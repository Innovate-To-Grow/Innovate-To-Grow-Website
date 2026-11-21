"""The rules ``update_ticket`` applies on every path that changes a ticket (its page, the bulk actions, replies).

- A group or assignee change that would leave the assignee outside a group with members raises ``AssignmentRefused``
  before anything changes: no field, no timeline entry, no assignment notice.
- A category's default group is given to a ticket without a group only when that group is active and the assignee
  (if any) belongs to it, or it has nobody in it; otherwise only the category is set, and nothing is refused.
- Reopening a resolved or closed ticket clears its resolution code and notes ("Resolution cleared on reopening (was:
  …)" on the timeline); closing a resolved ticket keeps them.
- A breach a staff change brings to light (a priority raised past its due times, a late move out of New, a pause
  after the resolution fell due) is on the timeline once, and not again while its flag stays set."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from ....models import AssignmentGroup, Ticket, TicketCategory, TicketEvent
from ....services import sla, tickets
from ....services.outbound import notifications
from ....services.tickets import events
from ...helpers import helpdesk_staff, make_admin
from ...helpers.service import Status, clocked_ticket, new_ticket

Kind = TicketEvent.Kind
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
COLUMNS = ("status", "impact", "priority", "category", "assignment_group", "assignee", "resolution_notes")


def row(ticket) -> tuple:
    return Ticket.objects.filter(pk=ticket.pk).values_list(*COLUMNS, "first_responded_at", "updated_at").get()


class _RuleCase(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.kim = make_admin(apps=["helpdesk"], email="kim@example.com", first_name="Kim", last_name="Lee")
        self.events = AssignmentGroup.objects.create(name="Events")
        self.events.members.add(self.kim)


class AssignmentRefusedTests(_RuleCase):
    def test_nothing_changes_when_the_new_group_and_assignee_do_not_fit(self):
        ticket = clocked_ticket()
        before = row(ticket)
        changes = {"status": Status.OPEN, "impact": 1, "urgency": 1, "resolution_notes": "Called back."}
        changes.update(category=TicketCategory.objects.create(name="Registration"), assignment_group=self.events)

        with (
            patch.object(notifications, "assignment_changed") as notice,
            self.assertRaisesMessage(tickets.AssignmentRefused, "Avery Agent is not a member of Events."),
        ):
            tickets.update_ticket(ticket, actor=self.agent, assignee=self.agent, **changes)

        self.assertEqual(row(ticket), before)
        self.assertFalse(TicketEvent.objects.exists())
        notice.assert_not_called()

    def test_a_new_group_or_a_new_assignee_alone_is_refused_too(self):
        assigned = new_ticket(assignee=self.agent)
        grouped = new_ticket(assignment_group=self.events, assignee=self.kim)
        before = [row(assigned), row(grouped)]

        with self.assertRaises(tickets.AssignmentRefused):
            tickets.update_ticket(assigned, actor=self.agent, assignment_group=self.events, priority="high")
        with self.assertRaises(tickets.AssignmentRefused):
            tickets.update_ticket(grouped, actor=self.agent, assignee=self.agent, status=Status.OPEN)

        self.assertEqual([row(assigned), row(grouped)], before)
        self.assertFalse(TicketEvent.objects.exists())
        # Unassigning in the same change lets the group in.
        changed = tickets.update_ticket(assigned, actor=self.agent, assignment_group=self.events, assignee=None)
        self.assertEqual(changed, ["assignment_group", "assignee"])


class CategoryDefaultGroupRuleTests(_RuleCase):
    def setUp(self):
        super().setUp()
        self.registration = TicketCategory.objects.create(name="Registration", default_group=self.events)

    def categorised(self, ticket, **changes):
        """What changed when ``ticket`` got the category (read afresh, as a form gives it), and its group then."""
        category = TicketCategory.objects.get(pk=self.registration.pk)
        changed = tickets.update_ticket(ticket, actor=self.agent, category=category, **changes)
        ticket.refresh_from_db()
        return changed, ticket.assignment_group

    def test_an_inactive_default_group_is_not_given(self):
        AssignmentGroup.objects.filter(pk=self.events.pk).update(is_active=False)

        self.assertEqual(self.categorised(new_ticket()), (["category"], None))

    def test_not_given_when_the_assignee_is_not_a_member(self):
        assigned = new_ticket(assignee=self.agent)
        assigning = new_ticket()

        self.assertEqual(self.categorised(assigned), (["category"], None))
        # Nor for an assignee chosen in the same change: the assignee is set, the group is not.
        self.assertEqual(self.categorised(assigning, assignee=self.agent), (["category", "assignee"], None))
        self.assertEqual(assigning.assignee, self.agent)
        self.assertFalse(TicketEvent.objects.filter(kind=Kind.GROUP).exists())

    def test_given_when_the_assignee_is_a_member_or_there_is_none(self):
        both = ["category", "assignment_group"]
        self.assertEqual(self.categorised(new_ticket(assignee=self.kim)), (both, self.events))
        self.assertEqual(self.categorised(new_ticket()), (both, self.events))
        self.assertEqual(self.categorised(new_ticket(), assignee=self.kim), ([*both, "assignee"], self.events))
        self.events.members.clear()  # a group with nobody in it takes any assignee
        self.assertEqual(self.categorised(new_ticket(assignee=self.agent)), (both, self.events))


class ReopeningClearsTheResolutionTests(_RuleCase):
    def done(self, status=Status.RESOLVED, code="solved", notes="Sent the times."):
        """A ticket answered and then resolved (or closed) with ``code`` and ``notes``."""
        now = timezone.now()
        values = {"closed_at": now, "resolved_at": now, "first_responded_at": now - HOUR}
        return new_ticket(status=status, resolution_code=code, resolution_notes=notes, **values)

    def cleared(self, ticket):
        event = ticket.events.get(kind=Kind.RESOLUTION)
        return event.actor, event.data, events.describe(event)

    def test_reopening_clears_the_code_and_the_notes(self):
        ticket = self.done()

        changed = tickets.update_ticket(ticket, actor=self.agent, status=Status.OPEN)

        ticket.refresh_from_db()
        self.assertEqual(changed, ["status", "resolution_code", "resolution_notes"])
        self.assertEqual((ticket.status, ticket.resolution_code, ticket.resolution_notes), (Status.OPEN, "", ""))
        cleared = "Resolution cleared on reopening (was: Solved)"
        self.assertEqual(self.cleared(ticket), (self.agent, {"cleared": "solved"}, cleared))
        self.assertEqual(list(ticket.events.values_list("kind", flat=True)), [Kind.STATUS, Kind.RESOLUTION])

    def test_the_bulk_reopen_clears_it_too(self):
        ticket = self.done(status=Status.CLOSED, code="information_provided", notes="")

        self.assertEqual(tickets.reopen([ticket], actor=self.agent), 1)

        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.resolution_code), (Status.OPEN, ""))
        cleared = "Resolution cleared on reopening (was: Information provided)"
        self.assertEqual(self.cleared(ticket), (self.agent, {"cleared": "information_provided"}, cleared))

    def test_closing_keeps_it_and_a_ticket_without_one_clears_nothing(self):
        resolved, bare = self.done(notes="Sent."), self.done(code="", notes="")

        self.assertEqual(tickets.close([resolved], actor=self.agent), 1)
        tickets.update_ticket(bare, actor=self.agent, status=Status.PENDING_INTERNAL)

        resolved.refresh_from_db()
        kept = (resolved.status, resolved.resolution_code, resolved.resolution_notes)
        self.assertEqual(kept, (Status.CLOSED, "solved", "Sent."))
        self.assertFalse(TicketEvent.objects.filter(kind=Kind.RESOLUTION).exists())


class BreachOnceTests(_RuleCase):
    def breaches(self, ticket) -> list[dict]:
        return list(ticket.events.filter(kind=Kind.SLA_BREACHED).values_list("data", flat=True))

    def test_a_priority_raised_past_both_due_times(self):
        ticket = clocked_ticket(started=timezone.now() - 10 * HOUR)  # moderate: 1 day to respond, 5 to resolve

        tickets.update_ticket(ticket, actor=self.agent, impact=1, urgency=1)  # critical: 1 h and 8 h, both past
        tickets.update_ticket(ticket, actor=self.agent, status=Status.OPEN)  # a late first response, flagged already

        ticket.refresh_from_db()
        self.assertEqual((ticket.response_breached, ticket.resolution_breached), (True, True))
        self.assertEqual(self.breaches(ticket), [{"which": "response"}, {"which": "resolution"}])

    def test_a_late_move_out_of_new_even_after_the_worker_flagged_it(self):
        started = timezone.now() - 2 * DAY  # the response fell due a day ago
        flagged = clocked_ticket(started=started)
        self.assertEqual(sla.mark_breaches(), 1)
        late = clocked_ticket(started=started)

        for ticket in (flagged, late):
            tickets.update_ticket(ticket, actor=self.agent, status=Status.OPEN)
            tickets.update_ticket(ticket, actor=self.agent, status=Status.PENDING_INTERNAL)

        for ticket in (flagged, late):
            ticket.refresh_from_db()
            self.assertEqual((ticket.response_breached, ticket.resolution_breached), (True, False))
            self.assertEqual(self.breaches(ticket), [{"which": "response"}])

    def test_a_pause_after_the_resolution_fell_due(self):
        now = timezone.now()
        ticket = clocked_ticket(started=now - 6 * DAY, status=Status.OPEN, first_responded_at=now - 6 * DAY)

        tickets.update_ticket(ticket, actor=self.agent, status=Status.PENDING_CUSTOMER)
        tickets.update_ticket(ticket, actor=self.agent, status=Status.RESOLVED, resolution_code="solved")

        ticket.refresh_from_db()
        self.assertEqual((ticket.response_breached, ticket.resolution_breached), (False, True))
        self.assertEqual(self.breaches(ticket), [{"which": "resolution"}])
