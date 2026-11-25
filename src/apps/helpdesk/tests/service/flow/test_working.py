"""Steps beside the ticket form (``services.tickets.working``): moving misclassified mail to the queue, assigning in
bulk, and internal notes.

- "Not automated: move to the queue" makes a ticket nobody answered yet New (moving it on is still its first
  response) and an answered one In progress. Automated mail's low impact and urgency (3 / 3) become a person's
  (2 / 2), with the priority they give; any other pair is kept. A ticket that never had an SLA clock gets one from
  now; a clock that stood still (spam) runs again, the time it stood still added to its resolution due time.
- ``assign`` returns how many tickets changed and how many it left as they were because the assignee is not a member
  of their group; unassigning is never refused.
- A note keeps every ordinary link whole, long ones too, and loses only a personal sign-in link."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from ....models import AssignmentGroup, Ticket, TicketEvent
from ....services import tickets
from ... import corpus
from ...helpers import helpdesk_staff, make_admin
from ...helpers.service import Status, clocked_ticket, new_ticket

Kind = TicketEvent.Kind
Priority = Ticket.Priority
HOUR = timedelta(hours=1)
REMOVED = "[sign-in link removed]"
FORMS = (
    "https://forms.office.com/Pages/ResponsePage.aspx?id="
    "pM_2PxXn20i44Qhnufn7o6ecLZTBorREjEcuPmpXb4pUQ0NBNFdSMEZBUVQ5UkpWNTZYTzdINUNDRi4u"
)


class MoveToQueueTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def moved(self, ticket) -> Ticket:
        self.assertEqual(tickets.move_to_queue([ticket], actor=self.agent), 1)
        ticket.refresh_from_db()
        return ticket

    def automated(self, **values) -> Ticket:
        values = {"impact": 3, "urgency": 3, "priority": Priority.LOW, **values}
        return new_ticket(
            automated=True, classification="auto_reply", status=Status.CLOSED, closed_at=timezone.now(), **values
        )

    def test_automated_mail_becomes_a_persons_new_ticket_with_a_clock_from_now(self):
        before = timezone.now()

        ticket = self.moved(self.automated())

        self.assertEqual((ticket.status, ticket.automated, ticket.unread), (Status.NEW, False, True))
        self.assertEqual((ticket.impact, ticket.urgency, ticket.priority), (2, 2, Priority.NORMAL))
        self.assertGreaterEqual(ticket.sla_started_at, before)
        self.assertEqual(ticket.response_due_at - ticket.sla_started_at, timedelta(days=1))  # moderate's targets
        self.assertEqual(ticket.resolution_due_at - ticket.sla_started_at, timedelta(days=5))
        self.assertEqual((ticket.sla_paused_at, ticket.first_responded_at), (None, None))
        self.assertEqual(ticket.events.get(kind=Kind.RECLASSIFIED).data, {"from": "auto_reply", "to": "human"})

    def test_an_impact_and_urgency_staff_chose_are_kept(self):
        ticket = self.moved(self.automated(impact=1, urgency=2, priority=Priority.HIGH))

        self.assertEqual((ticket.impact, ticket.urgency, ticket.priority), (1, 2, Priority.HIGH))
        self.assertEqual(ticket.response_due_at - ticket.sla_started_at, 4 * HOUR)  # high's targets

    def test_a_ticket_someone_answered_comes_back_in_progress(self):
        answered = new_ticket(status=Status.SPAM, first_responded_at=timezone.now() - HOUR, closed_at=timezone.now())

        ticket = self.moved(answered)

        self.assertEqual((ticket.status, ticket.closed_at), (Status.OPEN, None))

    def test_a_clock_that_stood_still_runs_again(self):
        ticket = clocked_ticket(started=timezone.now() - 3 * HOUR)
        self.assertEqual(tickets.mark_spam([ticket], actor=self.agent), 1)  # spam stops the clock
        Ticket.objects.filter(pk=ticket.pk).update(sla_paused_at=timezone.now() - 2 * HOUR)
        ticket.refresh_from_db()
        started, due = ticket.sla_started_at, ticket.resolution_due_at

        ticket = self.moved(ticket)

        self.assertEqual((ticket.status, ticket.sla_paused_at, ticket.sla_started_at), (Status.NEW, None, started))
        self.assertGreaterEqual(ticket.sla_paused_seconds, 2 * 3600)
        self.assertLess(ticket.sla_paused_seconds, 2 * 3600 + 60)
        self.assertEqual(ticket.resolution_due_at, due + timedelta(seconds=ticket.sla_paused_seconds))
        self.assertFalse(ticket.response_breached or ticket.resolution_breached)


class AssignTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def test_how_many_changed_and_how_many_were_left_as_they_were(self):
        kim = make_admin(email="kim@example.com", first_name="Kim", last_name="Lee")
        theirs = AssignmentGroup.objects.create(name="Technical")
        theirs.members.add(kim)
        mine = AssignmentGroup.objects.create(name="Events")
        mine.members.add(self.agent)
        selected = [
            new_ticket(assignee=self.agent),  # already theirs: no change
            new_ticket(assignment_group=mine),
            new_ticket(assignment_group=AssignmentGroup.objects.create(name="Nobody yet")),
            new_ticket(assignment_group=theirs),  # refused: not a member
        ]

        self.assertEqual(tickets.assign(selected, self.agent, actor=self.agent), (2, 1))
        self.assertEqual(Ticket.objects.filter(assignee=self.agent).count(), 3)
        self.assertEqual(tickets.assign(selected, None, actor=self.agent), (3, 0))  # unassigning is never refused
        self.assertFalse(Ticket.objects.filter(assignee__isnull=False).exists())


class NoteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def test_a_note_keeps_ordinary_links_and_loses_a_personal_sign_in_link(self):
        deep = f"www.example.org/files/{'a1B2' * 20}/plan.pdf"
        body = f"Form: {FORMS}\r\nPlan: {deep}\r\nTheir links: {corpus.LOGIN_LINK} {corpus.UNSUBSCRIBE_LINK}"

        note = tickets.add_note(new_ticket(), actor=self.agent, body=body)

        self.assertEqual(note.body_text, f"Form: {FORMS}\nPlan: {deep}\nTheir links: {REMOVED} {REMOVED}")

    def test_scrubbing_leaves_text_without_links_alone(self):
        token = "R" * 70  # a long run of letters outside a link is no link: kept

        self.assertEqual(tickets.scrub_sign_in_links(f"Ref {token}."), f"Ref {token}.")
        self.assertEqual(
            tickets.scrub_sign_in_links("https://i2g.ucmerced.edu/events"), "https://i2g.ucmerced.edu/events"
        )
