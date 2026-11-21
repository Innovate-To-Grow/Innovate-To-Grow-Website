"""A ticket's priority from its impact and urgency (ServiceNow's default matrix, on the helpdesk's four priorities).

=========  ==========  ==========  ==========
           Urgency 1   Urgency 2   Urgency 3
=========  ==========  ==========  ==========
Impact 1   1 Critical  2 High      3 Moderate
Impact 2   2 High      3 Moderate  4 Low
Impact 3   3 Moderate  4 Low       4 Low
=========  ==========  ==========  ==========

ServiceNow's fifth level ("5 – Planning", impact 3 × urgency 3) is folded into Low.
"""

from django.db.models import Case, IntegerField, Value, When

from ...models import Ticket

Priority = Ticket.Priority
# Lower score = more severe; impact + urgency runs from 2 (both high) to 6 (both low).
_BY_SCORE = {2: Priority.URGENT, 3: Priority.HIGH, 4: Priority.NORMAL, 5: Priority.LOW, 6: Priority.LOW}
# Severity order, most severe first (the stored values do not sort by severity).
SEVERITY = (Priority.URGENT, Priority.HIGH, Priority.NORMAL, Priority.LOW)
# Sorts rows with a ``priority`` column by severity (ascending: most severe first).
PRIORITY_RANK = Case(
    *(When(priority=value, then=Value(index)) for index, value in enumerate(SEVERITY)),
    default=Value(len(SEVERITY)),
    output_field=IntegerField(),
)
# The impact and urgency a new ticket starts with: moderate for a person's message, low for automated mail.
PERSON_DEFAULT = (Ticket.Impact.MEDIUM, Ticket.Urgency.MEDIUM)
AUTOMATED_DEFAULT = (Ticket.Impact.LOW, Ticket.Urgency.LOW)


def priority_for(impact: int, urgency: int) -> str:
    try:
        score = int(impact) + int(urgency)
    except (TypeError, ValueError):
        return Priority.NORMAL
    return _BY_SCORE.get(score, Priority.NORMAL)
