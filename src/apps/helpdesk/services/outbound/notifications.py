"""Emailing staff when a ticket is assigned to them, or to their group with nobody in it (ServiceNow's assignment
notifications). Only while sending is allowed (shadow mode off) and ``notify_assignment`` is on; never to the member
who made the change; only to active staff who still have the Helpdesk app. Queued when the change commits."""

from django.db import transaction

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


def _recipients(members, actor) -> list[str]:
    actor_pk = getattr(actor, "pk", None)
    addresses = [_address(member) for member in members if member.pk != actor_pk]
    return list(dict.fromkeys(address for address in addresses if address))


def assignment_changed(ticket: Ticket, *, actor, assignee_changed: bool, group_changed: bool) -> None:
    """After ``update_ticket`` changed the assignee or the group: queue the notification when it is due."""
    settings = HelpdeskSettings.load()
    if not settings.notify_assignment or not shadow.sending_allowed(settings):
        return
    ticket = Ticket.objects.select_related("assignee", "assignment_group").get(pk=ticket.pk)
    if assignee_changed and ticket.assignee_id:
        reason, recipients = "assigned", _recipients([ticket.assignee], actor)
    elif group_changed and ticket.assignment_group_id and not ticket.assignee_id:
        members = ticket.assignment_group.members.filter(is_active=True, is_staff=True)
        reason, recipients = "group", _recipients(list(members), actor)
    else:
        return
    if not recipients:
        return
    actor_name = compose.person(actor) or "The helpdesk"
    TicketEvent.objects.create(
        ticket=ticket, kind=TicketEvent.Kind.NOTIFIED, data={"reason": reason, "count": len(recipients)}
    )
    transaction.on_commit(
        lambda: jobs.enqueue_notice(ticket, recipients=recipients, reason=reason, actor_name=actor_name)
    )
