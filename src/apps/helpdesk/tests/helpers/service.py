"""Shared builders for the ServiceNow-style helpdesk tests: tickets with an SLA clock, and settings with sending on."""

from django.utils import timezone

from ...models import HelpdeskSettings, Ticket
from ...services import sla
from ..tickets.test_tickets import new_ticket

Status = Ticket.Status


def clocked_ticket(*, priority=Ticket.Priority.NORMAL, started=None, **values) -> Ticket:
    """A person's ticket whose SLA clock started at ``started`` (now by default), with ``priority``'s targets."""
    started = started or timezone.now()
    values.setdefault("first_message_at", started)
    return new_ticket(priority=priority, **sla.start_values(priority, started), **values)


def sending_settings(**values) -> HelpdeskSettings:
    """Saved settings with shadow mode off (sending allowed)."""
    values.setdefault("shadow_mode", False)
    return HelpdeskSettings.objects.create(**values)


__all__ = ["Status", "clocked_ticket", "new_ticket", "sending_settings"]
