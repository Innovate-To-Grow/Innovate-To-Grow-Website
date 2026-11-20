"""The SLA clock's values (start, priority change, first response, pause and resume) and how a clock is shown
(none, running, at risk, paused, breached, met), judged on unsaved tickets at a fixed "now"."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from ...models import SLATarget, Ticket
from ...services.tickets import sla

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

    def test_an_inactive_or_missing_target_gives_no_clock(self):
        SLATarget.objects.filter(priority=Ticket.Priority.HIGH).update(is_active=False)

        self.assertEqual(sla.start_values(Ticket.Priority.HIGH, NOW), {})
        self.assertEqual(sla.start_values("nonsense", NOW), {})
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


class StatusValuesTests(TestCase):
    def test_no_clock_never_pauses(self):
        self.assertEqual(sla.status_values(ticket(), Status.PENDING_CUSTOMER, NOW), {})

    def test_waiting_for_the_requester_or_resolving_pauses(self):
        for status in (Status.PENDING_CUSTOMER, Status.RESOLVED, Status.CLOSED):
            with self.subTest(status):
                self.assertEqual(sla.status_values(ticket(hours_ago=1), status, NOW), {"sla_paused_at": NOW})

    def test_pausing_after_the_due_time_breaches_the_resolution(self):
        values = sla.status_values(ticket(hours_ago=30), Status.RESOLVED, NOW)

        self.assertEqual(values, {"sla_paused_at": NOW, "resolution_breached": True})

    def test_moves_between_running_statuses_change_nothing(self):
        for status in (Status.NEW, Status.OPEN, Status.PENDING_INTERNAL):
            with self.subTest(status):
                self.assertEqual(sla.status_values(ticket(hours_ago=1), status, NOW), {})

    def test_moves_between_paused_statuses_change_nothing(self):
        paused = ticket(hours_ago=5, status=Status.PENDING_CUSTOMER, sla_paused_at=NOW - HOUR)

        self.assertEqual(sla.status_values(paused, Status.RESOLVED, NOW), {})

    def test_running_again_adds_the_time_it_stood_still(self):
        paused = ticket(hours_ago=5, sla_paused_at=NOW - 2 * HOUR, sla_paused_seconds=600)

        values = sla.status_values(paused, Status.OPEN, NOW)

        self.assertEqual(
            values,
            {
                "sla_paused_at": None,
                "sla_paused_seconds": 600 + 7200,
                "resolution_due_at": paused.resolution_due_at + 2 * HOUR,
            },
        )

    def test_a_pause_stamped_in_the_future_adds_nothing(self):
        paused = ticket(hours_ago=5, sla_paused_at=NOW + HOUR)

        values = sla.status_values(paused, Status.OPEN, NOW)

        self.assertEqual((values["sla_paused_seconds"], values["resolution_due_at"]), (0, paused.resolution_due_at))
        self.assertEqual(sla._standing_seconds(ticket(hours_ago=5), NOW), 0)  # a running clock stood still for none


class ResponseClockTests(TestCase):
    def test_states(self):
        cases = (
            ("no clock", ticket(), "none"),
            ("on track", ticket(hours_ago=1), "running"),
            ("75 % used", ticket(hours_ago=18), "at_risk"),
            ("overdue", ticket(hours_ago=25), "breached"),
            ("answered in time", ticket(hours_ago=25, first_responded_at=NOW - 20 * HOUR), "met"),
            ("answered late", ticket(hours_ago=25, first_responded_at=NOW, response_breached=True), "breached"),
            ("closed unanswered", ticket(hours_ago=25, status=Status.CLOSED), "none"),
            ("closed after breach", ticket(hours_ago=25, status=Status.CLOSED, response_breached=True), "breached"),
        )
        for name, subject, state in cases:
            with self.subTest(name):
                self.assertEqual(sla.response_clock(subject, NOW, 75).state, state)

    def test_the_warning_percent_moves_the_at_risk_line(self):
        half_used = ticket(hours_ago=12)

        self.assertEqual(sla.response_clock(half_used, NOW, 50).state, "at_risk")
        self.assertEqual(sla.response_clock(half_used, NOW, 51).state, "running")

    def test_the_clock_carries_its_due_time(self):
        subject = ticket(hours_ago=1)

        self.assertEqual(sla.response_clock(subject, NOW, 75).due, subject.response_due_at)


class ResolutionClockTests(TestCase):
    def test_states(self):
        paused = {"status": Status.PENDING_CUSTOMER, "sla_paused_at": NOW - HOUR}
        cases = (
            ("no clock", ticket(), "none"),
            ("on track", ticket(hours_ago=1, status=Status.OPEN), "running"),
            ("at risk", ticket(hours_ago=20, status=Status.OPEN), "at_risk"),
            ("overdue", ticket(hours_ago=25, status=Status.OPEN), "breached"),
            ("flagged", ticket(hours_ago=1, status=Status.OPEN, resolution_breached=True), "breached"),
            ("paused", ticket(hours_ago=2, **paused), "paused"),
            ("paused after breach", ticket(hours_ago=30, resolution_breached=True, **paused), "breached"),
            ("resolved in time", ticket(hours_ago=30, status=Status.RESOLVED), "met"),
            ("closed late", ticket(hours_ago=30, status=Status.CLOSED, resolution_breached=True), "breached"),
            ("spam", ticket(hours_ago=1, status=Status.SPAM), "none"),
            ("merged", ticket(hours_ago=1, status=Status.MERGED), "none"),
        )
        for name, subject, state in cases:
            with self.subTest(name):
                self.assertEqual(sla.resolution_clock(subject, NOW, 75).state, state)

    def test_paused_time_does_not_count_as_used(self):
        # Started 10 h ago with a 10 h target, of which 5 h stood still: 5 of 10 hours used.
        subject = ticket(
            status=Status.OPEN,
            sla_started_at=NOW - 10 * HOUR,
            resolution_due_at=NOW + 5 * HOUR,
            response_due_at=NOW,
            sla_paused_seconds=5 * 3600,
        )

        self.assertEqual(sla.resolution_clock(subject, NOW, 75).state, "running")
        self.assertEqual(sla.resolution_clock(subject, NOW, 50).state, "at_risk")


class CurrentClockTests(TestCase):
    def test_the_response_until_it_is_met_then_the_resolution(self):
        waiting = ticket(hours_ago=1)
        answered = ticket(hours_ago=1, status=Status.OPEN, first_responded_at=NOW)

        self.assertEqual(sla.current_clock(waiting, NOW, 75)[0], "Response")
        which, clock = sla.current_clock(answered, NOW, 75)
        self.assertEqual((which, clock.state), ("Resolution", "running"))

    def test_a_closed_ticket_shows_its_resolution(self):
        closed = ticket(hours_ago=30, status=Status.CLOSED)

        self.assertEqual(sla.current_clock(closed, NOW, 75)[0], "Resolution")

    def test_labels(self):
        labels = {
            state: sla.Clock(state).label for state in ("none", "running", "at_risk", "paused", "breached", "met")
        }

        self.assertEqual(
            labels,
            {
                "none": "No SLA",
                "running": "On track",
                "at_risk": "At risk",
                "paused": "Paused",
                "breached": "Breached",
                "met": "Met",
            },
        )
