"""The helpdesk's sending jobs, on the transactional email lane (claimed before campaign mail, paced by the facade).

- ``helpdesk.send_reply`` sends one stored reply or acknowledgement (``TicketMessage`` of ``Kind.REPLY``) that is
  still queued, and marks it sent; a staff reply then is the ticket's first response. A reply is never sent twice:
  a failure that leaves it uncertain whether the provider took the message is not retried (the reply is marked not
  confirmed), a refusal the provider reports as temporary is retried later, and only queued replies are sent.
- ``helpdesk.notify_staff`` (``notifications``) emails staff that a ticket was assigned to them or their group.

Both check shadow mode again when they run: a job queued before staff switched it back on sends nothing. A staff
reply that does not go out (failed, not confirmed, or stopped by a re-check) puts its ticket back in front of staff:
unread, and no longer waiting for the requester (who got nothing): New again when nobody answered it yet, else In
progress; the reason is on the timeline.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.core.services.background_jobs.delivery import provider_call_guard, provider_job_error

from ...models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from .. import sla
from ..tickets import shadow

logger = logging.getLogger(__name__)

REPLY_JOB_KIND = "helpdesk.send_reply"
NOTIFY_JOB_KIND = "helpdesk.notify_staff"
Delivery = TicketMessage.Delivery
Kind = TicketEvent.Kind
SHADOW_ON_ERROR = "Not sent: shadow mode was switched on before it went out."
FAILED_ERROR = (
    "Could not be sent: the mail service refused it, or every attempt failed. An I2G Master can see the details in "
    "Email Monitoring."
)
UNCERTAIN_ERROR = (
    "Not confirmed: the mail service did not confirm the reply, so it may or may not have arrived. Check Outlook's "
    "Sent Items before writing again."
)
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
        handler="apps.helpdesk.services.outbound.notifications.notify_staff_job",
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
    return TicketMessage.objects.filter(pk=message_id, delivery_status=Delivery.QUEUED).update(**values)


def _failed(message: TicketMessage, error: str, status: str = Delivery.FAILED) -> None:
    from ..tickets.changes import update_ticket

    with transaction.atomic():
        if not _mark(message.pk, status, error):
            return
        what = "acknowledgement" if message.automatic else "reply"
        data = {"what": what, "error": error, **({"uncertain": True} if status == Delivery.UNCERTAIN else {})}
        TicketEvent.objects.create(ticket_id=message.ticket_id, kind=Kind.REPLY_FAILED, data=data)
        ticket = Ticket.objects.filter(pk=message.ticket_id).first()
        if message.automatic or ticket is None:
            return
        if ticket.status == Ticket.Status.PENDING_CUSTOMER:
            # Back in front of staff: New again while nobody answered it yet (moving it on is still its first
            # response), else In progress. The system's own move is no response.
            back = Ticket.Status.NEW if ticket.first_responded_at is None else Ticket.Status.OPEN
            update_ticket(ticket, actor=None, status=back, reason="the reply did not go out", first_response=False)
        Ticket.objects.filter(pk=ticket.pk).update(unread=True)


def _sent(message: TicketMessage) -> None:
    """Mark the reply sent; a staff reply is the ticket's first response (judged at the time it went out)."""
    now = timezone.now()
    with transaction.atomic():
        if not _mark(message.pk, Delivery.SENT, delivered_at=now) or message.automatic:
            return
        ticket = Ticket.objects.select_for_update().filter(pk=message.ticket_id).first()
        values = sla.responded_values(ticket, now) if ticket is not None else {}
        if not values:
            return
        Ticket.objects.filter(pk=ticket.pk).update(**values, updated_at=now)
        TicketEvent.objects.create(ticket=ticket, kind=Kind.RESPONDED, actor=message.author, data={"by": "reply"})
        if values.get("response_breached") and not ticket.response_breached:
            TicketEvent.objects.create(ticket=ticket, kind=Kind.SLA_BREACHED, data={"which": "response"})


def send_reply_job(job) -> None:
    from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
    from apps.core.services.email import EmailMessage, deliver_email, email_tracking

    from . import compose, replies

    message = TicketMessage.objects.select_related("ticket").filter(pk=job.payload.get("message_id")).first()
    if message is None or message.kind != TicketMessage.Kind.REPLY or message.delivery_status != Delivery.QUEUED:
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
    mailbox = replies.reply_mailbox(ticket)
    reply_to = (mailbox,) if mailbox and mailbox.lower() != str(message.from_address).lower() else ()
    email = EmailMessage(
        subject=message.subject or compose.reply_subject(ticket),
        to=tuple(message.to_addresses),
        cc=tuple(message.cc_addresses),
        reply_to=reply_to,
        text_body=compose.reply_text(message.body_text, ticket, quoted),
        html_body=compose.reply_html(message.body_text, ticket, quoted),
        headers={"X-I2G-Ticket": ticket.display_number, **(compose.AUTOMATIC_HEADERS if message.automatic else {})},
    )
    category = "helpdesk_ack" if message.automatic else "helpdesk_reply"
    try:
        with email_tracking(category=category, source_type="helpdesk.ticketmessage", source_id=message.pk):
            deliver_email(email, before_provider_call=provider_call_guard(job))
    except ProviderDeliveryError as exc:
        raise provider_job_error(exc) from exc
    _sent(message)


def reply_job_state(job) -> None:
    from apps.core.models import BackgroundJob

    if job.status not in (BackgroundJob.Status.FAILED, BackgroundJob.Status.UNCERTAIN):
        return
    message = TicketMessage.objects.filter(pk=job.payload.get("message_id")).first()
    if message is None:
        return
    # The provider's own error stays in the job and the server log; staff get a fixed text (no provider detail).
    if job.status == BackgroundJob.Status.UNCERTAIN:
        _failed(message, UNCERTAIN_ERROR, Delivery.UNCERTAIN)
    else:
        _failed(message, FAILED_ERROR)
