"""Impact × urgency → priority (the full matrix), and what ``update_ticket`` does with the ServiceNow-style fields:
the priority it derives (and the SLA due times it re-judges), the category's default group, the resolution code and
notes, and the first response when a ticket leaves New."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from ....models import SLATarget, Ticket, TicketEvent
from ....services import tickets
from ....services.sla import priority
from ...helpers import helpdesk_staff
from ...helpers.service import clocked_ticket, new_ticket

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
