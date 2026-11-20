"""The SLA clock on real tickets: which new tickets get one (from the ingest), pausing and resuming it as staff and
the requester move the ticket, the queue's breached / due-soon queries, and the worker's breach marking."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from ....models import Ticket, TicketEvent
from ....services import sla
from ...helpers.service import Status, new_ticket

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

    def test_due_soon_lists_running_clocks_due_within_the_window(self):
        now = timezone.now()
        due_ticket(subject="response soon", response_in=2 * HOUR, resolution_in=90 * HOUR)
        due_ticket(subject="resolution soon", status=Status.OPEN, first_responded_at=now, resolution_in=5 * HOUR)
        due_ticket(
            subject="paused",
            status=Status.PENDING_CUSTOMER,
            first_responded_at=now,
            sla_paused_at=now,
            resolution_in=5 * HOUR,
        )
        due_ticket(subject="later", response_in=30 * HOUR, resolution_in=90 * HOUR)
        due_ticket(subject="overdue", response_in=-HOUR, resolution_in=90 * HOUR)
        due_ticket(subject="closed", status=Status.CLOSED, response_in=HOUR, resolution_in=HOUR)

        self.assertEqual(self.matching(sla.due_soon_q(now)), {"response soon", "resolution soon"})
        self.assertEqual(self.matching(sla.due_soon_q(now, hours=1)), set())
        self.assertEqual(self.matching(sla.due_soon_q(now, hours=48)), {"response soon", "resolution soon", "later"})


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
