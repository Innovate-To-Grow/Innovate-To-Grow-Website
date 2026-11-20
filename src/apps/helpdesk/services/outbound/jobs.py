"""The helpdesk's two sending jobs, on the transactional email lane (claimed before campaign mail, paced by the facade).

- ``helpdesk.send_reply`` sends one stored reply or acknowledgement (``TicketMessage`` of ``Kind.REPLY``) to the
  requester and marks it sent. A reply is never sent twice: the job is not retried once the provider call began
  (``can_retry_after_claim=False``), and a message already sent is skipped.
- ``helpdesk.notify_staff`` emails staff that a ticket was assigned to them (or to their group). It carries the
  ticket's number, subject and admin link, never the requester's message.

Both check shadow mode again when they run: a job queued before staff switched it back on sends nothing. When the
worker gives up on a reply (failed, or uncertain whether the provider took it), the state handler marks the message
failed and puts the reason on the ticket's timeline.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.core.services.background_jobs.delivery import provider_call_guard, provider_job_error

from ...models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ..tickets import shadow

logger = logging.getLogger(__name__)

REPLY_JOB_KIND = "helpdesk.send_reply"
NOTIFY_JOB_KIND = "helpdesk.notify_staff"
Delivery = TicketMessage.Delivery
SHADOW_ON_ERROR = "Not sent: shadow mode was switched on before it went out."
_ERROR_MAX = 255


def register_outbound() -> None:
    from apps.core.services.background_jobs import register_job_kind
    from apps.core.services.delivery_rates import Family, Lane

    register_job_kind(
        REPLY_JOB_KIND,
        handler="apps.helpdesk.services.outbound.jobs.send_reply_job",
        state_handler="apps.helpdesk.services.outbound.jobs.reply_job_state",
        family=Family.EMAIL,
        lane=Lane.TRANSACTIONAL,
    )
    register_job_kind(
        NOTIFY_JOB_KIND,
        handler="apps.helpdesk.services.outbound.jobs.notify_staff_job",
        family=Family.EMAIL,
        lane=Lane.TRANSACTIONAL,
    )


def enqueue_reply(message: TicketMessage):
    from apps.core.services.background_jobs import enqueue_job

    job, _created = enqueue_job(
        kind=REPLY_JOB_KIND,
        dedupe_key=f"reply:{message.pk}",
        payload={"message_id": str(message.pk)},
        can_retry_after_claim=False,
    )
    return job


def enqueue_notice(ticket: Ticket, *, recipients: list[str], reason: str, actor_name: str = ""):
    """Queue a notification to ``recipients`` (staff addresses) about ``ticket``; ``reason`` is assigned or group."""
    from apps.core.services.background_jobs import enqueue_job

    if not recipients:
        return None
    key = f"notify:{ticket.pk}:{reason}:{','.join(sorted(recipients))}:{timezone.now().isoformat()}"
    job, _created = enqueue_job(
        kind=NOTIFY_JOB_KIND,
        dedupe_key=key[:255],
        payload={"ticket_id": str(ticket.pk), "recipients": recipients, "reason": reason, "actor": actor_name},
        can_retry_after_claim=False,
    )
    return job


def _mark(message_id, status: str, error: str = "", **extra) -> int:
    values = {"delivery_status": status, "delivery_error": error[:_ERROR_MAX], "updated_at": timezone.now(), **extra}
    return TicketMessage.objects.filter(pk=message_id).exclude(delivery_status=Delivery.SENT).update(**values)


def _failed(message: TicketMessage, error: str) -> None:
    with transaction.atomic():
        if _mark(message.pk, Delivery.FAILED, error):
            kind = "acknowledgement" if message.automatic else "reply"
            TicketEvent.objects.create(
                ticket_id=message.ticket_id, kind=TicketEvent.Kind.REPLY_FAILED, data={"what": kind, "error": error}
            )


def send_reply_job(job) -> None:
    from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
    from apps.core.services.email import EmailMessage, deliver_email, email_tracking

    from . import compose, replies

    message = TicketMessage.objects.select_related("ticket").filter(pk=job.payload.get("message_id")).first()
    if message is None or message.kind != TicketMessage.Kind.REPLY or message.delivery_status == Delivery.SENT:
        return
    settings = HelpdeskSettings.load()
    if not shadow.sending_allowed(settings):
        _failed(message, SHADOW_ON_ERROR)
        return
    ticket = message.ticket
    # What allowed it when it was queued is judged again: the ticket may have been merged or marked spam since, or
    # the acknowledgement switched off.
    if ticket.status == Ticket.Status.MERGED or ticket.is_automated_or_spam:
        _failed(message, "Not sent: the ticket was merged, marked as spam or moved to automated mail meanwhile.")
        return
    if message.automatic and not settings.send_acknowledgement:
        _failed(message, "Not sent: the acknowledgement was switched off before it went out.")
        return
    quoted = None if message.automatic else replies.last_inbound(ticket)
    email = EmailMessage(
        subject=message.subject or compose.reply_subject(ticket),
        to=tuple(message.to_addresses),
        cc=tuple(message.cc_addresses),
        text_body=compose.reply_text(message.body_text, ticket),
        html_body=compose.reply_html(message.body_text, ticket, quoted),
        headers={"X-I2G-Ticket": ticket.display_number, **(compose.AUTOMATIC_HEADERS if message.automatic else {})},
    )
    category = "helpdesk_ack" if message.automatic else "helpdesk_reply"
    try:
        with email_tracking(category=category, source_type="helpdesk.ticketmessage", source_id=message.pk):
            deliver_email(email, before_provider_call=provider_call_guard(job))
    except ProviderDeliveryError as exc:
        raise provider_job_error(exc) from exc
    _mark(message.pk, Delivery.SENT, delivered_at=timezone.now())


def reply_job_state(job) -> None:
    from apps.core.models import BackgroundJob

    if job.status not in (BackgroundJob.Status.FAILED, BackgroundJob.Status.UNCERTAIN):
        return
    message = TicketMessage.objects.filter(pk=job.payload.get("message_id")).first()
    if message is None:
        return
    if job.status == BackgroundJob.Status.UNCERTAIN:
        error = "It is not certain the reply was delivered (the mail service did not confirm it). Check Outlook."
    else:
        # The provider's own error stays in the job and the server log; staff get a fixed text (no provider detail).
        error = "Could not be sent: the mail service refused it, or every attempt failed. See Email Monitoring."
    _failed(message, error)


def notify_staff_job(job) -> None:
    from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
    from apps.core.services.email import EmailMessage, deliver_email, email_tracking

    from . import compose

    ticket = Ticket.objects.filter(pk=job.payload.get("ticket_id")).first()
    recipients = tuple(job.payload.get("recipients") or ())
    if ticket is None or not recipients or not shadow.sending_allowed(HelpdeskSettings.load()):
        return
    reason = job.payload.get("reason")
    actor = job.payload.get("actor") or "Someone"
    if reason == "group":
        group = ticket.assignment_group.name if ticket.assignment_group_id else "your group"
        what, lead = "Assigned to your group", f"{actor} assigned {ticket.display_number} to {group}."
    else:
        what, lead = "Assigned to you", f"{actor} assigned {ticket.display_number} to you."
    text = (
        f"{lead}\n\nSubject: {ticket.subject or '(no subject)'}\nRequester: {ticket.requester_email}\n"
        f"Priority: {ticket.get_priority_display()}\n\nOpen the ticket: {compose.ticket_admin_url(ticket)}\n"
    )
    email = EmailMessage(subject=compose.notice_subject(ticket, what), to=recipients, text_body=text)
    try:
        with email_tracking(category="helpdesk_notice", source_type="helpdesk.ticket", source_id=ticket.pk):
            deliver_email(email, before_provider_call=provider_call_guard(job))
    except ProviderDeliveryError as exc:
        raise provider_job_error(exc) from exc
