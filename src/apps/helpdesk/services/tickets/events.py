"""Writing a ticket's audit trail (``TicketEvent``) and describing an event in one line for the timeline."""

from ...models import Ticket, TicketEvent

Kind = TicketEvent.Kind
_STATUS = dict(Ticket.Status.choices)
_PRIORITY = dict(Ticket.Priority.choices)
_RESOLUTION = dict(Ticket.ResolutionCode.choices)
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


_IMPACT = dict(Ticket.Impact.choices)
_URGENCY = dict(Ticket.Urgency.choices)


def _label(value) -> str:
    return str(value or "")


def record_changes(current: Ticket, values: dict, *, actor, name) -> None:
    """One entry per field ``update_ticket`` changes (``values``, against the row ``current``), in a fixed order;
    ``name`` labels a member (the assignee)."""
    fields = (
        ("impact", Kind.IMPACT, lambda value: _IMPACT.get(value, value)),
        ("urgency", Kind.URGENCY, lambda value: _URGENCY.get(value, value)),
        ("priority", Kind.PRIORITY, None),
        ("category", Kind.CATEGORY, _label),
        ("assignment_group", Kind.GROUP, _label),
        ("assignee", Kind.ASSIGNED, name),
    )
    for field, kind, labels in fields:
        if field in values:
            before, after = getattr(current, field), values[field]
            if labels is not None:
                before, after = labels(before), labels(after)
            record(current, kind, actor=actor, **{"from": before, "to": after})
    if "resolution_code" in values or "resolution_notes" in values:
        code = values.get("resolution_code", current.resolution_code)
        if not code and not values.get("resolution_notes") and current.resolution_code:
            # Reopening clears the resolution (``changes.reopen_values``).
            record(current, Kind.RESOLUTION, actor=actor, cleared=current.resolution_code)
            return
        record(current, Kind.RESOLUTION, actor=actor, code=code, notes="resolution_notes" in values)


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
    moved = int(data.get("messages") or 0)
    return f"I2G-#{data.get('source')} merged into this ticket ({moved} message{'s' if moved != 1 else ''} moved)"


def _resolution(event, data) -> str:
    if data.get("cleared"):
        return f"Resolution cleared on reopening (was: {_RESOLUTION.get(data['cleared'], data['cleared'])})"
    code = _RESOLUTION.get(data.get("code") or "", "") or "no code"
    return f"Resolution: {code}" + (" (notes updated)" if data.get("notes") else "")


def _notified(event, data) -> str:
    if data.get("reason") == "group":
        count = int(data.get("count") or 0)
        return f"Assignment notice emailed to the group's {count} member{'s' if count != 1 else ''}"
    return "Assignment notice emailed to the assignee"


def _responded(event, data) -> str:
    return "First response: " + ("a reply was sent" if data.get("by") == "reply" else "the ticket was moved on")


def _reply_failed(event, data) -> str:
    what = "acknowledgement" if data.get("what") == "acknowledgement" else "reply"
    error = str(data.get("error") or "delivery failed")
    for lead in ("Not sent: ", "Could not be sent: ", "Not confirmed: "):
        error = error.removeprefix(lead)
    if data.get("uncertain"):
        return f"The {what} may not have been delivered: {error}"
    return f"The {what} was not sent: {error}"


def _breached(event, data) -> str:
    which = data.get("which") or "resolution"
    if data.get("cleared"):
        return f"SLA breach cleared: the {which} is within the new priority's target"
    return f"SLA breached: the {which} is overdue"


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
    Kind.IMPACT: lambda event, data: f"Impact: {_change(data)}",
    Kind.URGENCY: lambda event, data: f"Urgency: {_change(data)}",
    Kind.GROUP: lambda event, data: f"{event.get_kind_display()}: {_change(data)}",
    Kind.RESOLUTION: _resolution,
    Kind.REPLY: lambda event, data: f"Reply sent to {data.get('to') or 'the requester'}",
    Kind.ACKNOWLEDGED: lambda event, data: f"Acknowledgement sent to {data.get('to') or 'the requester'}",
    Kind.REPLY_FAILED: _reply_failed,
    Kind.NOTIFIED: _notified,
    Kind.RESPONDED: _responded,
    Kind.SLA_BREACHED: _breached,
}


def describe(event: TicketEvent) -> str:
    """One line for the timeline, built only from the event's own fields (never from message content)."""
    describer = _DESCRIBERS.get(event.kind)
    return describer(event, event.data or {}) if describer is not None else event.get_kind_display()
