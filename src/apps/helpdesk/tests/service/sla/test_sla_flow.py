"""The SLA clock on real tickets: which new tickets get one (from the ingest), pausing and resuming it as staff and
the requester move the ticket, the queue's breached / due-soon queries, and the worker's breach marking."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from ....models import SLATarget, Ticket, TicketEvent
from ....services import tickets
from ... import corpus
from ...helpers import FakeReader, helpdesk_staff, receive
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


class NewTicketClockTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_persons_new_ticket_starts_moderate_with_its_clock_at_arrival(self):
        ticket = receive(corpus.message())

        self.assertEqual((ticket.impact, ticket.urgency, ticket.priority), (2, 2, Ticket.Priority.NORMAL))
        self.assertEqual(ticket.sla_started_at, ticket.first_message_at)
        self.assertEqual(ticket.response_due_at, ticket.sla_started_at + timedelta(minutes=1440))
        self.assertEqual(ticket.resolution_due_at, ticket.sla_started_at + timedelta(minutes=7200))

    def test_automated_mail_starts_low_without_a_clock(self):
        ticket = receive(corpus.out_of_office())

        self.assertEqual((ticket.impact, ticket.urgency, ticket.priority), (3, 3, Ticket.Priority.LOW))
        self.assertEqual((ticket.sla_started_at, ticket.response_due_at, ticket.resolution_due_at), (None, None, None))

    def test_backfilled_mail_has_no_clock(self):
        ticket = receive(corpus.message(), received=timezone.now() - timedelta(days=3))

        self.assertTrue(ticket.backfilled)
        self.assertIsNone(ticket.sla_started_at)

    def test_a_priority_whose_target_is_off_has_no_clock(self):
        SLATarget.objects.filter(priority=Ticket.Priority.NORMAL).update(is_active=False)

        ticket = receive(corpus.message())

        self.assertEqual((ticket.sla_started_at, ticket.response_due_at), (None, None))


class PauseAndResumeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def stood_still_since(self, ticket, when):
        Ticket.objects.filter(pk=ticket.pk).update(sla_paused_at=when)
        ticket.refresh_from_db()

    def test_waiting_for_the_requester_pauses_and_running_again_adds_the_pause(self):
        ticket = clocked_ticket(status=Status.OPEN)
        due = ticket.resolution_due_at

        tickets.update_ticket(ticket, actor=self.agent, status=Status.PENDING_CUSTOMER)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.sla_paused_at)
        self.stood_still_since(ticket, timezone.now() - 2 * HOUR)

        tickets.update_ticket(ticket, actor=self.agent, status=Status.OPEN)

        ticket.refresh_from_db()
        self.assertIsNone(ticket.sla_paused_at)
        self.assertAlmostEqual(ticket.sla_paused_seconds, 7200, delta=5)
        self.assertAlmostEqual((ticket.resolution_due_at - due).total_seconds(), 7200, delta=5)

    def test_resolving_pauses_and_a_late_resolution_is_breached(self):
        ticket = clocked_ticket(status=Status.OPEN, started=timezone.now() - timedelta(days=6))

        tickets.update_ticket(ticket, actor=self.agent, status=Status.RESOLVED, resolution_code="solved")

        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.sla_paused_at)
        self.assertTrue(ticket.resolution_breached)

    def test_a_priority_change_with_a_pause_is_judged_on_the_new_due_time(self):
        ticket = clocked_ticket(status=Status.OPEN, started=timezone.now() - 10 * HOUR)

        tickets.update_ticket(ticket, actor=self.agent, impact=1, urgency=1, status=Status.PENDING_CUSTOMER)

        ticket.refresh_from_db()
        self.assertEqual(ticket.resolution_due_at, ticket.sla_started_at + timedelta(minutes=480))
        self.assertIsNotNone(ticket.sla_paused_at)
        self.assertTrue(ticket.resolution_breached)

    def test_the_requesters_reply_runs_a_waiting_clock_again(self):
        reader = FakeReader()
        ticket = receive(corpus.message(), reader=reader)
        tickets.update_ticket(ticket, actor=self.agent, status=Status.PENDING_CUSTOMER)
        self.stood_still_since(ticket, timezone.now() - 3 * HOUR)
        due = ticket.resolution_due_at

        receive(corpus.message(message_id="<r1@x>", in_reply_to="<m1@mail.example.org>"), reader=reader)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Status.OPEN)
        self.assertIsNone(ticket.sla_paused_at)
        self.assertAlmostEqual(ticket.sla_paused_seconds, 3 * 3600, delta=5)
        self.assertAlmostEqual((ticket.resolution_due_at - due).total_seconds(), 3 * 3600, delta=5)

    def test_a_reply_that_reopens_a_resolved_ticket_continues_its_clock(self):
        reader = FakeReader()
        ticket = receive(corpus.message(), reader=reader)
        tickets.update_ticket(ticket, actor=self.agent, status=Status.RESOLVED, resolution_code="solved")
        self.stood_still_since(ticket, timezone.now() - HOUR)

        receive(corpus.message(message_id="<r2@x>", in_reply_to="<m1@mail.example.org>"), reader=reader)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Status.OPEN)
        self.assertIsNone(ticket.sla_paused_at)
        self.assertAlmostEqual(ticket.sla_paused_seconds, 3600, delta=5)
