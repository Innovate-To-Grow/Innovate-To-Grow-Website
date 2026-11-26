"""The SLA's record over a ticket's life, as the second live check left it: a breach a new priority's target no longer
has is cleared on the timeline (and a later one recorded again), the queue column shows a breach of either clock, a
status change counts as the first response while a clocked ticket has none, and moving a ticket to the queue resets
only automated mail's impact and urgency."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from ....models import Ticket, TicketEvent
from ....services import sla, tickets
from ....services.tickets import events
from ...helpers import helpdesk_staff
from ...helpers.service import Status, clocked_ticket, new_ticket

Kind = TicketEvent.Kind
Priority = Ticket.Priority


class BreachHistoryTests(TestCase):
    def setUp(self):
        self.agent = helpdesk_staff()

    def lines(self, ticket, which: str) -> list[str]:
        found = ticket.events.filter(kind=Kind.SLA_BREACHED, data__which=which).order_by("created_at")
        return [events.describe(event) for event in found]

    def test_a_breach_the_new_priority_does_not_have_is_cleared_on_record_and_a_new_one_recorded_again(self):
        ticket = clocked_ticket(started=timezone.now() - timedelta(hours=30))  # Moderate: response due after 1 day
        tickets.update_ticket(ticket, actor=self.agent, impact=1, urgency=1)  # Critical: overdue at once
        tickets.update_ticket(ticket, actor=self.agent, impact=3, urgency=3)  # Low: 3 days, not overdue
        ticket.refresh_from_db()
        self.assertFalse(ticket.response_breached)

        tickets.update_ticket(ticket, actor=self.agent, impact=1, urgency=1)

        ticket.refresh_from_db()
        self.assertTrue(ticket.response_breached)
        self.assertEqual(
            self.lines(ticket, "response"),
            [
                "SLA breached: the response is overdue",
                "SLA breach cleared: the response is within the new priority's target",
                "SLA breached: the response is overdue",
            ],
        )
        cleared = ticket.events.get(kind=Kind.SLA_BREACHED, data__cleared=True, data__which="response")
        self.assertEqual(cleared.actor, self.agent)

    def test_the_queue_column_shows_an_overdue_resolution_beside_the_response_it_shows(self):
        started = timezone.now() - timedelta(days=6)  # Moderate: response 1 day, resolution 5 days: both overdue
        ticket = clocked_ticket(started=started)
        self.assertFalse(ticket.response_breached or ticket.resolution_breached)  # nothing flagged yet

        state, text = sla.queue_label(ticket, timezone.now(), 75)

        self.assertEqual((state, text), ("breached", "Response & Resolution breached"))


class FirstResponseTests(TestCase):
    def setUp(self):
        self.agent = helpdesk_staff()

    def test_a_clocked_ticket_without_a_response_is_answered_by_any_move(self):
        ticket = clocked_ticket(status=Status.OPEN)  # e.g. back from a reply that did not go out

        tickets.update_ticket(ticket, actor=self.agent, status=Status.PENDING_INTERNAL)

        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.first_responded_at)
        self.assertTrue(ticket.events.filter(kind=Kind.RESPONDED, data={"by": "status"}).exists())

    def test_a_ticket_from_before_the_sla_is_answered_only_by_leaving_new(self):
        old = new_ticket(status=Status.OPEN)
        tickets.update_ticket(old, actor=self.agent, status=Status.PENDING_INTERNAL)
        old.refresh_from_db()
        self.assertIsNone(old.first_responded_at)
        self.assertFalse(old.events.filter(kind=Kind.RESPONDED).exists())

        new = new_ticket()
        tickets.update_ticket(new, actor=self.agent, status=Status.OPEN)
        new.refresh_from_db()
        self.assertIsNotNone(new.first_responded_at)


class MoveToQueueTests(TestCase):
    def setUp(self):
        self.agent = helpdesk_staff()

    def test_a_persons_ticket_marked_spam_keeps_the_impact_urgency_and_due_times_staff_gave_it(self):
        ticket = clocked_ticket(priority=Priority.LOW, impact=3, urgency=3)
        tickets.mark_spam([ticket], actor=self.agent)
        ticket.refresh_from_db()
        due = (ticket.response_due_at, ticket.priority)

        self.assertEqual(tickets.move_to_queue([ticket], actor=self.agent), 1)

        ticket.refresh_from_db()
        self.assertEqual((ticket.impact, ticket.urgency), (3, 3))
        self.assertEqual((ticket.response_due_at, ticket.priority), due)
        self.assertFalse(ticket.events.filter(kind__in=(Kind.IMPACT, Kind.URGENCY, Kind.PRIORITY)).exists())

    def test_automated_mail_moved_to_the_queue_starts_where_a_persons_message_does_on_record(self):
        mail = new_ticket(
            automated=True,
            status=Status.CLOSED,
            classification="auto_reply",
            impact=3,
            urgency=3,
            priority=Priority.LOW,
        )

        tickets.move_to_queue([mail], actor=self.agent)

        mail.refresh_from_db()
        self.assertEqual((mail.impact, mail.urgency, mail.priority, mail.status), (2, 2, Priority.NORMAL, Status.NEW))
        self.assertIsNotNone(mail.response_due_at)
        kinds = set(mail.events.values_list("kind", flat=True))
        self.assertTrue({Kind.IMPACT, Kind.URGENCY, Kind.PRIORITY} <= kinds)
