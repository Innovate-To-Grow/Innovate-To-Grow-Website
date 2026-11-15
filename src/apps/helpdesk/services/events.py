"""Writing a ticket's audit trail (``TicketEvent``) and describing an event in one line for the timeline."""

from ..models import Ticket, TicketEvent

Kind = TicketEvent.Kind
_STATUS = dict(Ticket.Status.choices)
_PRIORITY = dict(Ticket.Priority.choices)
_RULES = {
    "references": "threaded by its In-Reply-To / References",
    "subject_token": "threaded by the ticket number in its subject",
    "conversation": "threaded by its Outlook conversation",
    "reopened": "reopened the ticket",
    "flood": "grouped: many tickets from this sender",
    "new": "",
    "related": "",
    "follow_up": "",
}


def record(ticket: Ticket, kind: str, *, actor=None, **data) -> TicketEvent:
    return TicketEvent.objects.create(ticket=ticket, kind=kind, actor=actor, data=data)


def _change(data: dict, labels: dict | None = None) -> str:
    labels = labels or {}
    before, after = data.get("from"), data.get("to")
    return f"{labels.get(before, before) or '—'} → {labels.get(after, after) or '—'}"


def _created(event, data) -> str:
    return "Ticket opened as automated mail (closed at once)" if data.get("automated") else "Ticket opened"


def _message(event, data) -> str:
    rule = _RULES.get(data.get("rule", ""), "")
    sender = data.get("from") or "unknown sender"
    return f"{event.get_kind_display()} from {sender}" + (f" ({rule})" if rule else "")


def _status(event, data) -> str:
    reason = f" ({data['reason']})" if data.get("reason") else ""
    return f"{event.get_kind_display()}: {_change(data, _STATUS)}{reason}"


def _merged(event, data) -> str:
    if data.get("into"):
        return f"Merged into I2G-#{data['into']}"
    return f"I2G-#{data.get('source')} merged into this ticket ({data.get('messages', 0)} messages moved)"


_DESCRIBERS = {
    Kind.CREATED: _created,
    Kind.CUSTOMER_MESSAGE: _message,
    Kind.AUTOMATED_MESSAGE: _message,
    Kind.STATUS: _status,
    Kind.REOPENED: _status,
    Kind.PRIORITY: lambda event, data: f"Priority: {_change(data, _PRIORITY)}",
    Kind.CATEGORY: lambda event, data: f"{event.get_kind_display()}: {_change(data)}",
    Kind.ASSIGNED: lambda event, data: f"{event.get_kind_display()}: {_change(data)}",
    Kind.MERGED: _merged,
    Kind.RELATED: lambda event, data: (
        f"Related ticket: I2G-#{data.get('number')} ({data.get('reason') or 'same conversation'})"
    ),
    Kind.MENTION: lambda event, data: (
        f"The message names I2G-#{data.get('number')}, but its sender is not a participant of that ticket"
    ),
    Kind.FLOOD: lambda event, data: (
        f"Grouped into this ticket: many new tickets from {data.get('from') or 'one sender'}"
    ),
}


def describe(event: TicketEvent) -> str:
    """One line for the timeline, built only from the event's own fields (never from message content)."""
    describer = _DESCRIBERS.get(event.kind)
    return describer(event, event.data or {}) if describer is not None else event.get_kind_display()
