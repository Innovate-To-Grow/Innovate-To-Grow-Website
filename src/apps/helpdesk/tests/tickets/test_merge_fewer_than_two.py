from apps.core.services.db_tools.safe_orm import ActionRequestError, resolve_model
from apps.helpdesk.tests.tickets.test_merge import BOUNCE_SENDER, Kind, Status, _MergeServiceCase, make_ticket

from ...admin.tickets import timeline
from ...models import Ticket, TicketEvent, TicketMessage
from ...services import tickets
from .. import corpus
from ..helpers import FakeReader, receive


class MergeServiceTests(_MergeServiceCase):
    def test_fewer_than_two_tickets_is_no_merge_and_no_refusal(self):
        bounce = make_ticket("Undeliverable", automated=True, hours_ago=5)
        merged = make_ticket("Merged", status=Status.MERGED)

        for selection in ([], [bounce], [bounce, bounce], [bounce, merged]):
            with self.subTest(len(selection)):
                self.assertEqual(tickets.merge_refusal(selection), "")
                self.assertIsNone(tickets.merge(selection, actor=self.agent))
        self.assertFalse(TicketEvent.objects.exists())

    def test_peoples_tickets_still_merge_into_the_oldest(self):
        older = make_ticket("Parking", hours_ago=5, unread=False, assignee=self.agent)
        newer = make_ticket("Parking again", requester="kim@example.org", participants=["kim@example.org", "lee@x.org"])
        tickets.add_note(newer, actor=self.agent, body="Same question as the other ticket.")
        newer.refresh_from_db()

        target = tickets.merge([newer, older], actor=self.agent)

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(target.pk, older.pk)
        self.assertEqual((newer.status, newer.merged_into), (Status.MERGED, older))
        self.assertEqual(older.messages.count(), 3)
        self.assertEqual(older.participants, ["pat@example.org", "kim@example.org", "lee@x.org"])
        self.assertEqual(older.last_activity_at, newer.last_activity_at)
        self.assertEqual((older.status, older.unread, older.assignee), (Status.OPEN, False, self.agent))
        self.assertEqual(older.events.get(kind=Kind.MERGED).data, {"source": newer.number, "messages": 2})
        self.assertEqual(newer.events.get(kind=Kind.MERGED).data, {"into": older.number})

    def test_automated_mail_merged_into_a_persons_ticket_changes_nothing_but_its_timeline(self):
        person = make_ticket("Did you get my registration?", hours_ago=5, unread=False, status=Status.PENDING_CUSTOMER)
        bounce = make_ticket("Undeliverable", requester=BOUNCE_SENDER, automated=True, hours_ago=1)
        before = Ticket.objects.get(pk=person.pk)
        bounce_closed_at = bounce.closed_at

        target = tickets.merge([bounce, person], actor=self.agent)

        person.refresh_from_db()
        bounce.refresh_from_db()
        self.assertEqual(target.pk, person.pk)
        unchanged = ("status", "unread", "participants", "last_activity_at", "automated", "closed_at", "priority")
        for name in unchanged:
            self.assertEqual(getattr(person, name), getattr(before, name), name)
        self.assertNotIn(BOUNCE_SENDER, person.participants)
        self.assertEqual(
            list(person.messages.values_list("kind", flat=True)),
            [TicketMessage.Kind.CUSTOMER, TicketMessage.Kind.AUTOMATED],
        )
        self.assertIn("automated", [entry.kind for entry in timeline.build(person)])  # shown collapsed
        # The automated ticket stays hidden mail: still automated, closed when it arrived, now merged.
        self.assertEqual(
            (bounce.status, bounce.merged_into, bounce.automated, bounce.closed_at, bounce.unread),
            (Status.MERGED, person, True, bounce_closed_at, False),
        )
        self.assertTrue(bounce.is_automated_or_spam)
        self.assertEqual(person.events.get(kind=Kind.MERGED).data, {"source": bounce.number, "messages": 1})

    def test_later_automated_mail_of_a_merged_thread_joins_the_persons_ticket_without_changing_it(self):
        reader = FakeReader()
        person = receive(corpus.message(sender="Alex Kim <alex.kim@contoso.example>"), reader=reader)
        reply = receive(corpus.out_of_office(), reader=reader)  # its own ticket: no thread names the person's
        tickets.merge([reply, person], actor=self.agent)
        tickets.mark_read([person])
        before = Ticket.objects.get(pk=person.pk)

        joined = receive(
            corpus.out_of_office(message_id="<oof-2@contoso.example>", in_reply_to="<oof-1@contoso.example>"),
            reader=reader,
        )

        self.assertEqual(joined.pk, person.pk)
        for name in ("status", "unread", "participants", "last_activity_at", "closed_at"):
            self.assertEqual(getattr(joined, name), getattr(before, name), name)
        self.assertEqual(joined.messages.filter(kind=TicketMessage.Kind.AUTOMATED).count(), 2)

    def test_a_merged_ticket_is_never_moved_to_the_queue(self):
        person = make_ticket("Question", hours_ago=5)
        bounce = make_ticket("Undeliverable", requester=BOUNCE_SENDER, automated=True)
        tickets.merge([person, bounce], actor=self.agent)
        bounce.refresh_from_db()

        self.assertEqual(tickets.move_to_queue([bounce], actor=self.agent), 0)

        bounce.refresh_from_db()
        self.assertEqual((bounce.status, bounce.automated, bounce.unread), (Status.MERGED, True, False))
        self.assertFalse(bounce.events.filter(kind=Kind.RECLASSIFIED).exists())

    def test_the_cli_and_the_assistant_cannot_reach_tickets_at_all(self):
        # /admin-api/ (the i2g-admin CLI) and the AI assistant resolve every model through safe_orm.
        for model_name in ("ticket", "ticketmessage"):
            with self.subTest(model_name), self.assertRaises(ActionRequestError):
                resolve_model("helpdesk", model_name, write=True)
