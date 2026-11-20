"""Emailing staff when a ticket is assigned to them, or to their group with nobody in it (ServiceNow's assignment
notifications). Only while sending is allowed (shadow mode off) and ``notify_assignment`` is on; only for a person's
ticket (not automated mail, spam or a merged ticket); never to the member who made the change; only to active staff
who still have the Helpdesk app; never for an inactive group. Queued when the change commits, and judged again by
the job when it runs (``notify_staff_job``): the timeline records the notice once it went out.

A notice carries the ticket's number, subject (anything link-like removed), requester, priority and admin link, never
the requester's message, and asks not to be answered: an answer would reach the helpdesk mailbox as a ticket.
"""

from django.db import transaction

from apps.core.services.background_jobs.delivery import provider_call_guard, provider_job_error
from apps.core.utils.access import user_can_access_app
from apps.core.utils.security import is_plain_address

from ...models import HelpdeskSettings, Ticket, TicketEvent
from ..tickets import shadow
from . import compose, jobs


def _address(member) -> str:
    if member is None or not member.is_active or not user_can_access_app(member, "helpdesk"):
        return ""
    address = member.get_primary_email()
    return address if is_plain_address(address) else ""


def _recipients(members, actor=None) -> list[str]:
    actor_pk = getattr(actor, "pk", None)
    addresses = [_address(member) for member in members if member.pk != actor_pk]
    return list(dict.fromkeys(address for address in addresses if address))


def _due(ticket: Ticket | None, settings: HelpdeskSettings) -> bool:
    if ticket is None or not settings.notify_assignment or not shadow.sending_allowed(settings):
        return False
    return not ticket.is_automated_or_spam and ticket.status != Ticket.Status.MERGED


def _intended(ticket: Ticket, reason: str, actor=None) -> list[str]:
    """Who the notice for ``reason`` goes to now: the assignee, or the active group's members while it has nobody."""
    if reason == "assigned":
        return _recipients([ticket.assignee], actor) if ticket.assignee_id else []
    group = ticket.assignment_group
    if ticket.assignee_id or group is None or not group.is_active:
        return []
    return _recipients(list(group.members.filter(is_active=True, is_staff=True)), actor)


def assignment_changed(ticket: Ticket, *, actor, assignee_changed: bool, group_changed: bool) -> None:
    """After ``update_ticket`` changed the assignee or the group: queue the notification when it is due."""
    settings = HelpdeskSettings.load()
    ticket = Ticket.objects.select_related("assignee", "assignment_group").get(pk=ticket.pk)
    if not _due(ticket, settings):
        return
    if assignee_changed and ticket.assignee_id:
        reason = "assigned"
    elif group_changed and ticket.assignment_group_id and not ticket.assignee_id:
        reason = "group"
    else:
        return
    recipients = _intended(ticket, reason, actor)
    if not recipients:
        return
    actor_name = compose.person(actor) or "The helpdesk"
    transaction.on_commit(
        lambda: jobs.enqueue_notice(ticket, recipients=recipients, reason=reason, actor_name=actor_name)
    )


def notify_staff_job(job) -> None:
    from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
    from apps.core.services.email import EmailMessage, deliver_email, email_tracking

    ticket = (
        Ticket.objects.select_related("assignee", "assignment_group").filter(pk=job.payload.get("ticket_id")).first()
    )
    if not _due(ticket, HelpdeskSettings.load()):
        return
    reason = job.payload.get("reason")
    # Still the people it was meant for (the assignment may have changed, a grant ended, the group been switched off).
    still = set(_intended(ticket, reason))
    recipients = tuple(address for address in job.payload.get("recipients") or () if address in still)
    if not recipients:
        return
    actor = job.payload.get("actor") or "Someone"
    if reason == "group":
        what, lead = "Assigned to your group", f"{actor} assigned {ticket.display_number} to {ticket.assignment_group}."
    else:
        what, lead = "Assigned to you", f"{actor} assigned {ticket.display_number} to you."
    text = (
        f"{lead}\n\nSubject: {compose.without_links(ticket.subject, strict=True) or '(no subject)'}\n"
        f"Requester: {ticket.requester_email}\nPriority: {ticket.get_priority_display()}\n\n"
        f"Open the ticket: {compose.ticket_admin_url(ticket)}\n\n"
        "This is an automatic notice: please do not reply to it (a reply would open a new ticket). Work on the ticket "
        "in the admin.\n"
    )
    email = EmailMessage(
        subject=compose.notice_subject(ticket, what), to=recipients, text_body=text, headers=compose.NOTICE_HEADERS
    )
    try:
        with email_tracking(category="helpdesk_notice", source_type="helpdesk.ticket", source_id=ticket.pk):
            deliver_email(email, before_provider_call=provider_call_guard(job))
    except ProviderDeliveryError as exc:
        raise provider_job_error(exc) from exc
    TicketEvent.objects.create(
        ticket=ticket, kind=TicketEvent.Kind.NOTIFIED, data={"reason": reason, "count": len(recipients)}
    )
