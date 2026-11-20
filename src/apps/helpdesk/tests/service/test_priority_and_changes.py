"""Impact × urgency → priority (the full matrix), and what ``update_ticket`` does with the ServiceNow-style fields:
the priority it derives (and the SLA due times it re-judges), the category's default group, the resolution code and
notes, and the first response when a ticket leaves New."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from ...models import AssignmentGroup, SLATarget, Ticket, TicketCategory, TicketEvent
from ...services import tickets
from ...services.tickets import priority
from ...services.tickets.changes import RESOLUTION_NOTES_MAX_CHARS
from ..helpers import helpdesk_staff
from .support import Status, clocked_ticket, new_ticket

Kind = TicketEvent.Kind
Priority = Ticket.Priority


class PriorityMatrixTests(TestCase):
    MATRIX = {
        (1, 1): Priority.URGENT,
        (1, 2): Priority.HIGH,
        (1, 3): Priority.NORMAL,
        (2, 1): Priority.HIGH,
        (2, 2): Priority.NORMAL,
        (2, 3): Priority.LOW,
        (3, 1): Priority.NORMAL,
        (3, 2): Priority.LOW,
        (3, 3): Priority.LOW,
    }

    def test_every_impact_and_urgency_pair(self):
        for (impact, urgency), expected in self.MATRIX.items():
            with self.subTest(impact=impact, urgency=urgency):
                self.assertEqual(priority.priority_for(impact, urgency), expected)

    def test_string_values_from_a_form_count_as_numbers(self):
        self.assertEqual(priority.priority_for("1", "1"), Priority.URGENT)

    def test_values_that_are_not_numbers_or_off_the_matrix_give_moderate(self):
        for impact, urgency in ((None, 1), ("x", 2), (0, 0), (9, 9)):
            with self.subTest(impact=impact, urgency=urgency):
                self.assertEqual(priority.priority_for(impact, urgency), Priority.NORMAL)

    def test_defaults_and_severity_order(self):
        self.assertEqual(priority.priority_for(*priority.PERSON_DEFAULT), Priority.NORMAL)
        self.assertEqual(priority.priority_for(*priority.AUTOMATED_DEFAULT), Priority.LOW)
        self.assertEqual(priority.SEVERITY, (Priority.URGENT, Priority.HIGH, Priority.NORMAL, Priority.LOW))


class ImpactUrgencyChangeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def test_impact_and_urgency_set_the_priority_and_are_recorded_with_labels(self):
        ticket = new_ticket()

        changed = tickets.update_ticket(ticket, actor=self.agent, impact=1, urgency=1)

        ticket.refresh_from_db()
        self.assertEqual(changed, ["impact", "urgency", "priority"])
        self.assertEqual((ticket.impact, ticket.urgency, ticket.priority), (1, 1, Priority.URGENT))
        self.assertEqual(ticket.events.get(kind=Kind.IMPACT).data, {"from": "2 – Medium", "to": "1 – High"})
        self.assertEqual(ticket.events.get(kind=Kind.URGENCY).data, {"from": "2 – Medium", "to": "1 – High"})
        self.assertEqual(ticket.events.get(kind=Kind.PRIORITY).data, {"from": "normal", "to": "urgent"})

    def test_a_change_that_keeps_the_priority_records_no_priority_change(self):
        ticket = new_ticket()  # impact 2 × urgency 2: moderate

        changed = tickets.update_ticket(ticket, actor=self.agent, impact=1, urgency=3)  # still moderate

        self.assertEqual(changed, ["impact", "urgency"])
        self.assertFalse(ticket.events.filter(kind=Kind.PRIORITY).exists())

    def test_impact_and_urgency_win_over_a_priority_given_with_them(self):
        ticket = new_ticket()

        tickets.update_ticket(ticket, actor=self.agent, urgency=1, priority=Priority.LOW)

        ticket.refresh_from_db()
        self.assertEqual(ticket.priority, Priority.HIGH)

    def test_a_priority_given_alone_is_kept_as_given(self):
        ticket = new_ticket()

        self.assertEqual(tickets.update_ticket(ticket, actor=self.agent, priority=Priority.URGENT), ["priority"])
        ticket.refresh_from_db()
        self.assertEqual((ticket.impact, ticket.priority), (2, Priority.URGENT))


class PriorityResetsTheClockTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.started = timezone.now() - timedelta(hours=10)
        self.ticket = clocked_ticket(started=self.started)

    def test_a_higher_priority_sets_tighter_targets_from_the_same_start_and_judges_them(self):
        tickets.update_ticket(self.ticket, actor=self.agent, impact=1, urgency=1)  # urgent: 60 / 480 minutes

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.response_due_at, self.started + timedelta(minutes=60))
        self.assertEqual(self.ticket.resolution_due_at, self.started + timedelta(minutes=480))
        self.assertTrue(self.ticket.response_breached)
        self.assertTrue(self.ticket.resolution_breached)

    def test_a_lower_priority_judges_both_again_and_clears_the_flags(self):
        tickets.update_ticket(self.ticket, actor=self.agent, impact=1, urgency=1)
        tickets.update_ticket(self.ticket, actor=self.agent, impact=2, urgency=2)  # back to moderate: 1440 / 7200

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.response_due_at, self.started + timedelta(minutes=1440))
        self.assertEqual(self.ticket.resolution_due_at, self.started + timedelta(minutes=7200))
        self.assertFalse(self.ticket.response_breached)
        self.assertFalse(self.ticket.resolution_breached)

    def test_paused_time_stays_added_to_the_new_resolution_due_time(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(sla_paused_seconds=3600)
        self.ticket.refresh_from_db()

        tickets.update_ticket(self.ticket, actor=self.agent, priority=Priority.HIGH)  # 240 / 2880 minutes

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.resolution_due_at, self.started + timedelta(minutes=2880, hours=1))

    def test_a_priority_whose_target_is_off_has_no_due_times(self):
        SLATarget.objects.filter(priority=Priority.LOW).update(is_active=False)
        tickets.update_ticket(self.ticket, actor=self.agent, impact=1, urgency=1)

        tickets.update_ticket(self.ticket, actor=self.agent, impact=3, urgency=3)

        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.response_due_at, self.ticket.resolution_due_at), (None, None))
        self.assertEqual((self.ticket.response_breached, self.ticket.resolution_breached), (False, False))
        self.assertEqual(self.ticket.sla_started_at, self.started)

    def test_a_ticket_without_a_clock_gets_none_from_a_priority_change(self):
        unclocked = new_ticket()

        tickets.update_ticket(unclocked, actor=self.agent, impact=1, urgency=1)

        unclocked.refresh_from_db()
        self.assertEqual((unclocked.sla_started_at, unclocked.response_due_at), (None, None))


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
