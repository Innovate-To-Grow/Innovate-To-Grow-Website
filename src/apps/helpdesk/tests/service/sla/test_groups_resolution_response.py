"""Impact × urgency → priority (the full matrix), and what ``update_ticket`` does with the ServiceNow-style fields:
the priority it derives (and the SLA due times it re-judges), the category's default group, the resolution code and
notes, and the first response when a ticket leaves New."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from ....models import AssignmentGroup, Ticket, TicketCategory, TicketEvent
from ....services import tickets
from ....services.tickets.changes import RESOLUTION_NOTES_MAX_CHARS
from ...helpers import helpdesk_staff
from ...helpers.service import Status, clocked_ticket, new_ticket

Kind = TicketEvent.Kind
Priority = Ticket.Priority


class CategoryDefaultGroupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.events = AssignmentGroup.objects.create(name="Events")
        self.category = TicketCategory.objects.create(name="Registration", default_group=self.events)

    def test_the_category_assigns_its_group_to_a_ticket_without_one(self):
        ticket = new_ticket()

        changed = tickets.update_ticket(ticket, actor=self.agent, category=self.category)

        ticket.refresh_from_db()
        self.assertEqual(changed, ["category", "assignment_group"])
        self.assertEqual(ticket.assignment_group, self.events)
        self.assertEqual(ticket.events.get(kind=Kind.GROUP).data, {"from": "", "to": "Events"})

    def test_a_ticket_with_a_group_keeps_it(self):
        technical = AssignmentGroup.objects.create(name="Technical")
        ticket = new_ticket(assignment_group=technical)

        self.assertEqual(tickets.update_ticket(ticket, actor=self.agent, category=self.category), ["category"])
        ticket.refresh_from_db()
        self.assertEqual(ticket.assignment_group, technical)

    def test_a_group_chosen_with_the_category_wins(self):
        technical = AssignmentGroup.objects.create(name="Technical")
        ticket = new_ticket()

        tickets.update_ticket(ticket, actor=self.agent, category=self.category, assignment_group=technical)

        ticket.refresh_from_db()
        self.assertEqual(ticket.assignment_group, technical)

    def test_a_category_without_a_default_group_assigns_none(self):
        ticket = new_ticket()

        tickets.update_ticket(ticket, actor=self.agent, category=TicketCategory.objects.create(name="Other"))

        ticket.refresh_from_db()
        self.assertIsNone(ticket.assignment_group)


class ResolutionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.ticket = new_ticket(status=Status.OPEN)

    def test_resolving_records_the_code_and_the_cleaned_notes(self):
        changed = tickets.update_ticket(
            self.ticket,
            actor=self.agent,
            status=Status.RESOLVED,
            resolution_code=Ticket.ResolutionCode.SOLVED,
            resolution_notes="  Sent the\x00 schedule.  ",
        )

        self.ticket.refresh_from_db()
        self.assertEqual(changed, ["status", "resolution_code", "resolution_notes"])
        self.assertEqual(self.ticket.resolution_notes, "Sent the schedule.")
        self.assertIsNotNone(self.ticket.resolved_at)
        event = self.ticket.events.get(kind=Kind.RESOLUTION)
        self.assertEqual((event.actor, event.data), (self.agent, {"code": "solved", "notes": True}))

    def test_a_code_alone_records_that_no_notes_changed(self):
        tickets.update_ticket(self.ticket, actor=self.agent, resolution_code=Ticket.ResolutionCode.DUPLICATE)

        self.assertEqual(self.ticket.events.get(kind=Kind.RESOLUTION).data, {"code": "duplicate", "notes": False})

    def test_unchanged_notes_and_code_record_nothing(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(resolution_notes="Done", resolution_code="solved")
        self.ticket.refresh_from_db()

        changed = tickets.update_ticket(
            self.ticket, actor=self.agent, resolution_code="solved", resolution_notes=" Done "
        )

        self.assertEqual(changed, [])
        self.assertFalse(self.ticket.events.exists())

    def test_notes_are_cut_at_their_limit(self):
        tickets.update_ticket(self.ticket, actor=self.agent, resolution_notes="x" * 25000)

        self.ticket.refresh_from_db()
        self.assertEqual(len(self.ticket.resolution_notes), RESOLUTION_NOTES_MAX_CHARS)


class FirstResponseByStatusTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def test_leaving_new_is_the_first_response_once(self):
        ticket = clocked_ticket()

        tickets.update_ticket(ticket, actor=self.agent, status=Status.OPEN)
        tickets.update_ticket(ticket, actor=self.agent, status=Status.PENDING_INTERNAL)

        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.first_responded_at)
        self.assertFalse(ticket.response_breached)
        responded = ticket.events.get(kind=Kind.RESPONDED)
        self.assertEqual((responded.actor, responded.data), (self.agent, {"by": "status"}))

    def test_leaving_new_after_the_due_time_breaches_the_response(self):
        ticket = clocked_ticket(started=timezone.now() - timedelta(days=2))

        tickets.update_ticket(ticket, actor=self.agent, status=Status.OPEN)

        ticket.refresh_from_db()
        self.assertTrue(ticket.response_breached)

    def test_lowering_the_priority_while_leaving_new_judges_the_response_by_the_new_target(self):
        # Critical (1 h to respond) for two hours, then moderate (1 day) and In progress in one save: in time.
        ticket = clocked_ticket(
            priority=Ticket.Priority.URGENT, impact=1, urgency=1, started=timezone.now() - timedelta(hours=2)
        )

        tickets.update_ticket(ticket, actor=self.agent, impact=2, urgency=2, status=Status.OPEN)

        ticket.refresh_from_db()
        self.assertEqual(ticket.priority, Ticket.Priority.NORMAL)
        self.assertIsNotNone(ticket.first_responded_at)
        self.assertFalse(ticket.response_breached)

    def test_marking_a_new_ticket_spam_is_no_response(self):
        ticket = clocked_ticket()

        tickets.update_ticket(ticket, actor=self.agent, status=Status.SPAM)

        ticket.refresh_from_db()
        self.assertIsNone(ticket.first_responded_at)
        self.assertFalse(ticket.events.filter(kind=Kind.RESPONDED).exists())
