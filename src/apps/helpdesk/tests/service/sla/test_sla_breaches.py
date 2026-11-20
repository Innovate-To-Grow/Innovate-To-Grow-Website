"""The queue's breached and at-risk queries (at risk: a running clock past the warning share of its priority's
target, not overdue yet), and the worker's breach marking."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from ....models import SLATarget, Ticket, TicketEvent
from ....services import sla
from ...helpers.service import Status, clocked_ticket, new_ticket

Kind = TicketEvent.Kind
HOUR = timedelta(hours=1)


def due_ticket(*, response_in=None, resolution_in=None, **values) -> Ticket:
    """A ticket whose response / resolution fall due ``response_in`` / ``resolution_in`` from now (timedelta)."""
    now = timezone.now()
    values.setdefault("sla_started_at", now - 100 * HOUR)
    if response_in is not None:
        values["response_due_at"] = now + response_in
    if resolution_in is not None:
        values["resolution_due_at"] = now + resolution_in
    return new_ticket(**values)


class QueueQueryTests(TestCase):
    def setUp(self):
        cache.clear()

    def matching(self, q):
        return set(Ticket.objects.filter(q).values_list("subject", flat=True))

    def test_breached_lists_flagged_and_overdue_clocks(self):
        now = timezone.now()
        due_ticket(subject="flagged", response_breached=True, response_in=HOUR)
        due_ticket(subject="response overdue", response_in=-HOUR, resolution_in=HOUR)
        due_ticket(subject="resolution overdue", status=Status.OPEN, first_responded_at=now, resolution_in=-HOUR)
        due_ticket(subject="answered", first_responded_at=now, response_in=-HOUR, resolution_in=HOUR)
        due_ticket(
            subject="paused",
            status=Status.PENDING_CUSTOMER,
            first_responded_at=now,
            sla_paused_at=now,
            resolution_in=-HOUR,
        )
        due_ticket(subject="closed", status=Status.CLOSED, response_in=-HOUR, resolution_in=-HOUR)
        due_ticket(subject="on track", response_in=HOUR, resolution_in=2 * HOUR)
        new_ticket(subject="no clock")

        self.assertEqual(self.matching(sla.breached_q(now)), {"flagged", "response overdue", "resolution overdue"})

    def test_at_risk_lists_running_clocks_past_the_warning_share_of_their_own_span(self):
        now = timezone.now()
        ago = lambda hours: now - timedelta(hours=hours)  # noqa: E731
        # Moderate: 24 h to respond, 5 days to resolve.
        clocked_ticket(subject="response at risk", started=ago(20))  # 83 % of the response used
        responded = {"status": Status.OPEN, "first_responded_at": ago(100)}
        clocked_ticket(subject="resolution at risk", started=ago(108), **responded)  # 90 % of the resolution
        clocked_ticket(
            subject="paused", started=ago(108), sla_paused_at=now, **{**responded, "status": Status.PENDING_CUSTOMER}
        )
        clocked_ticket(subject="on track", started=ago(14))  # 58 %
        clocked_ticket(subject="overdue", started=ago(25))
        clocked_ticket(subject="closed", started=ago(20), status=Status.CLOSED)
        clocked_ticket(subject="critical", priority=Ticket.Priority.URGENT, started=now - timedelta(minutes=10))

        self.assertEqual(self.matching(sla.at_risk_q(now, 75)), {"response at risk", "resolution at risk"})
        self.assertEqual(self.matching(sla.at_risk_q(now, 50)), {"response at risk", "resolution at risk", "on track"})
        self.assertEqual(self.matching(sla.at_risk_q(now, 99)), set())

    def test_each_clock_is_judged_by_its_own_span_whatever_the_target_is_now(self):
        """As the queue's SLA column reads it: a clock set under a 2-day target is 42 % used after 20 h, though the
        target is 1 day now."""
        now = timezone.now()
        SLATarget.objects.filter(priority=Ticket.Priority.NORMAL).update(response_minutes=48 * 60)
        clocked_ticket(subject="two-day clock", started=now - timedelta(hours=20))
        SLATarget.objects.filter(priority=Ticket.Priority.NORMAL).update(response_minutes=24 * 60)

        self.assertEqual(self.matching(sla.at_risk_q(now, 75)), set())
        self.assertEqual(self.matching(sla.at_risk_q(now, 40)), {"two-day clock"})

    def test_a_clock_without_due_times_is_never_at_risk(self):
        SLATarget.objects.filter(priority=Ticket.Priority.NORMAL).update(is_active=False)
        clocked_ticket(subject="target off", started=timezone.now() - timedelta(hours=20))

        self.assertEqual(self.matching(sla.at_risk_q(timezone.now(), 1)), set())


class MarkBreachesTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_each_overdue_clock_is_flagged_once_with_an_entry(self):
        now = timezone.now()
        response = due_ticket(response_in=-HOUR, resolution_in=HOUR)
        resolution = due_ticket(status=Status.OPEN, first_responded_at=now, response_in=-HOUR, resolution_in=-HOUR)

        self.assertEqual(sla.mark_breaches(), 2)
        self.assertEqual(sla.mark_breaches(), 0)

        response.refresh_from_db()
        resolution.refresh_from_db()
        self.assertEqual((response.response_breached, response.resolution_breached), (True, False))
        self.assertEqual((resolution.response_breached, resolution.resolution_breached), (False, True))
        self.assertEqual(
            list(response.events.filter(kind=Kind.SLA_BREACHED).values_list("data", flat=True)), [{"which": "response"}]
        )
        self.assertEqual(
            list(resolution.events.filter(kind=Kind.SLA_BREACHED).values_list("data", flat=True)),
            [{"which": "resolution"}],
        )

    def test_answered_paused_closed_and_on_track_tickets_are_left_alone(self):
        now = timezone.now()
        answered = due_ticket(first_responded_at=now, response_in=-HOUR, resolution_in=HOUR)
        paused = due_ticket(
            status=Status.PENDING_CUSTOMER, first_responded_at=now, sla_paused_at=now, resolution_in=-HOUR
        )
        closed = due_ticket(status=Status.CLOSED, response_in=-HOUR, resolution_in=-HOUR)
        on_track = due_ticket(response_in=HOUR, resolution_in=HOUR)

        self.assertEqual(sla.mark_breaches(), 0)
        for ticket in (answered, paused, closed, on_track):
            ticket.refresh_from_db()
            self.assertFalse(ticket.response_breached or ticket.resolution_breached)
        self.assertFalse(TicketEvent.objects.filter(kind=Kind.SLA_BREACHED).exists())

    def test_judged_at_the_given_time(self):
        due_ticket(response_in=HOUR, resolution_in=10 * HOUR)

        self.assertEqual(sla.mark_breaches(now=timezone.now() + 2 * HOUR), 1)

    def test_a_stop_request_ends_it_before_the_next_ticket(self):
        due_ticket(response_in=-HOUR, resolution_in=HOUR)

        self.assertEqual(sla.mark_breaches(should_stop=lambda: True), 0)
        self.assertFalse(Ticket.objects.filter(response_breached=True).exists())
