"""The SLA clock's values (start, priority change, first response, pause and resume) and how a clock is shown
(none, running, at risk, paused, breached, met), judged on unsaved tickets at a fixed "now"."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from ....models import SLATarget, Ticket
from ....services import sla

Status = Ticket.Status
NOW = timezone.now()
HOUR = timedelta(hours=1)


def ticket(**values) -> Ticket:
    """An unsaved ticket; ``hours_ago`` starts its clock that long before NOW with ``target_hours`` to resolve it."""
    hours_ago = values.pop("hours_ago", None)
    target = values.pop("target_hours", 24)
    if hours_ago is not None:
        start = NOW - hours_ago * HOUR
        values.setdefault("sla_started_at", start)
        values.setdefault("response_due_at", start + target * HOUR)
        values.setdefault("resolution_due_at", start + target * HOUR)
    return Ticket(**values)


class StartTests(TestCase):
    def test_the_seeded_targets(self):
        targets = dict(SLATarget.objects.values_list("priority", "response_minutes"))
        resolutions = dict(SLATarget.objects.values_list("priority", "resolution_minutes"))
        self.assertEqual(targets, {"urgent": 60, "high": 240, "normal": 1440, "low": 4320})
        self.assertEqual(resolutions, {"urgent": 480, "high": 2880, "normal": 7200, "low": 14400})

    def test_a_new_ticket_gets_both_due_times_from_its_start(self):
        values = sla.start_values(Ticket.Priority.HIGH, NOW)

        self.assertEqual(
            values,
            {
                "sla_started_at": NOW,
                "response_due_at": NOW + timedelta(minutes=240),
                "resolution_due_at": NOW + timedelta(minutes=2880),
            },
        )

    def test_an_inactive_or_missing_target_gives_a_start_without_due_times(self):
        SLATarget.objects.filter(priority=Ticket.Priority.HIGH).update(is_active=False)

        self.assertEqual(sla.start_values(Ticket.Priority.HIGH, NOW), {"sla_started_at": NOW})
        self.assertEqual(sla.start_values("nonsense", NOW), {"sla_started_at": NOW})
        self.assertIsNone(sla.target_for(Ticket.Priority.HIGH))


class PriorityValuesTests(TestCase):
    def test_a_ticket_without_a_clock_keeps_none(self):
        self.assertEqual(sla.priority_values(ticket(), Ticket.Priority.URGENT, NOW), {})

    def test_a_response_made_is_judged_against_the_new_due_time(self):
        responded = ticket(hours_ago=3, first_responded_at=NOW - HOUR)  # answered 2 h after the start

        urgent = sla.priority_values(responded, Ticket.Priority.URGENT, NOW)  # 1 h to respond
        high = sla.priority_values(responded, Ticket.Priority.HIGH, NOW)  # 4 h to respond

        self.assertTrue(urgent["response_breached"])
        self.assertFalse(high["response_breached"])
        self.assertEqual(high["response_due_at"], responded.sla_started_at + 4 * HOUR)

    def test_a_paused_resolution_is_judged_at_its_pause(self):
        paused = ticket(hours_ago=10, sla_paused_at=NOW - 5 * HOUR)

        values = sla.priority_values(paused, Ticket.Priority.URGENT, NOW)  # 8 h to resolve, paused after 5 h

        self.assertFalse(values["resolution_breached"])


class RespondedValuesTests(TestCase):
    def test_in_time_is_met(self):
        self.assertEqual(sla.responded_values(ticket(hours_ago=1), NOW), {"first_responded_at": NOW})

    def test_late_is_breached(self):
        late = sla.responded_values(ticket(hours_ago=30), NOW)

        self.assertEqual(late, {"first_responded_at": NOW, "response_breached": True})

    def test_only_the_first_response_counts(self):
        self.assertEqual(sla.responded_values(ticket(hours_ago=30, first_responded_at=NOW - HOUR), NOW), {})

    def test_a_ticket_without_a_clock_still_records_its_first_response(self):
        self.assertEqual(sla.responded_values(ticket(), NOW), {"first_responded_at": NOW})
