from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.helpdesk.tests.ingest.test_ingest_rules import Kind, Status, event_kinds

from ...models import HelpdeskSettings, Ticket, TicketMessage
from .. import corpus
from ..helpers import FakeReader, ingest, queue, receive


class ThreadingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.reader = FakeReader()
        self.first = receive(corpus.message(cc="kim@example.org"), reader=self.reader, conversation="CONV-1")

    def reply(self, **values):
        values.setdefault("message_id", f"<r{TicketMessage.objects.count()}@mail.example.org>")
        conversation = values.pop("conversation", "")
        return receive(corpus.message(**values), reader=self.reader, conversation=conversation)

    def test_a_reply_joins_by_references_and_marks_the_ticket_unread(self):
        Ticket.objects.filter(pk=self.first.pk).update(unread=False, status=Status.PENDING_CUSTOMER)

        joined = self.reply(sender="Lee <lee@example.org>", references="<root@x> <m1@mail.example.org>")

        self.assertEqual(joined.pk, self.first.pk)
        self.assertEqual((joined.status, joined.unread), (Status.OPEN, True))
        self.assertIn("lee@example.org", joined.participants)
        self.assertGreaterEqual(joined.last_activity_at, self.first.last_activity_at)
        self.assertEqual(event_kinds(joined), [Kind.CREATED, Kind.CUSTOMER_MESSAGE, Kind.STATUS])

    def test_a_reply_soon_after_closing_reopens_the_ticket(self):
        Ticket.objects.filter(pk=self.first.pk).update(
            status=Status.RESOLVED, closed_at=timezone.now(), resolved_at=timezone.now()
        )

        reopened = self.reply(in_reply_to="<m1@mail.example.org>")

        self.assertEqual(reopened.pk, self.first.pk)
        self.assertEqual((reopened.status, reopened.closed_at, reopened.resolved_at), (Status.OPEN, None, None))
        self.assertIn(Kind.REOPENED, event_kinds(reopened))

    def test_a_reply_long_after_closing_opens_a_linked_follow_up(self):
        closed_at = timezone.now() - timedelta(days=HelpdeskSettings().reopen_window_days + 1)
        Ticket.objects.filter(pk=self.first.pk).update(status=Status.CLOSED, closed_at=closed_at)

        follow_up = self.reply(in_reply_to="<m1@mail.example.org>")

        self.assertNotEqual(follow_up.pk, self.first.pk)
        self.assertEqual(follow_up.related_ticket_id, self.first.pk)
        related = self.first.events.get(kind=Kind.RELATED)
        self.assertEqual(related.data, {"number": follow_up.number, "reason": "follow-up after the ticket closed"})

    def test_the_subject_token_works_only_for_participants(self):
        token = f"Re: Question [I2G-#{self.first.number}]"

        joined = self.reply(subject=token, sender="kim@example.org")
        stranger = self.reply(subject=token, sender="stranger@evil.example")

        self.assertEqual(joined.pk, self.first.pk)
        self.assertNotEqual(stranger.pk, self.first.pk)
        mention = stranger.events.get(kind=Kind.MENTION)
        self.assertEqual(mention.data, {"number": self.first.number})

    def test_a_token_without_brackets_and_in_any_case_threads_too(self):
        joined = self.reply(subject=f"about i2g-#{self.first.number} again")

        self.assertEqual(joined.pk, self.first.pk)

    def test_the_conversation_id_works_only_for_participants(self):
        joined = self.reply(conversation="CONV-1")
        stranger = self.reply(conversation="CONV-1", sender="someone@else.example")

        self.assertEqual(joined.pk, self.first.pk)
        self.assertNotEqual(stranger.pk, self.first.pk)

    def test_a_persons_reply_prefers_their_human_ticket_over_an_automated_one(self):
        receive(corpus.out_of_office(sender="Pat Doe <pat@example.org>"), reader=self.reader, conversation="CONV-1")

        joined = self.reply(conversation="CONV-1")

        self.assertEqual(joined.pk, self.first.pk)

    def test_a_merged_ticket_is_followed(self):
        target = receive(corpus.message(sender="other@example.org", message_id="<t@x>"), reader=self.reader)
        Ticket.objects.filter(pk=self.first.pk).update(status=Status.MERGED, merged_into=target)

        joined = self.reply(in_reply_to="<m1@mail.example.org>")

        self.assertEqual(joined.pk, target.pk)


class DuplicateTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_second_copy_of_a_message_is_not_stored_or_even_fetched(self):
        reader = FakeReader()
        first = receive(corpus.message(), reader=reader)
        second_copy = queue(corpus.message(), reader=reader)
        fetched_before = len(reader.fetched)

        ingest(reader)

        second_copy.refresh_from_db()
        self.assertEqual(len(reader.fetched), fetched_before)
        self.assertEqual(second_copy.result, {"ticket": first.number, "duplicate": True})
        self.assertEqual(TicketMessage.objects.count(), 1)

    def test_a_message_without_a_message_id_is_recognised_by_its_content(self):
        reader = FakeReader()
        first = receive(corpus.message(message_id=None), reader=reader)
        again = queue(corpus.message(message_id=None), reader=reader)

        ingest(reader)

        again.refresh_from_db()
        self.assertEqual(again.result["ticket"], first.number)
        self.assertTrue(again.result["duplicate"])
        self.assertEqual(TicketMessage.objects.count(), 1)


class FloodTests(TestCase):
    def setUp(self):
        cache.clear()
        HelpdeskSettings.objects.create(flood_threshold=2, flood_window_minutes=60)

    def test_more_new_tickets_than_the_threshold_from_one_sender_are_grouped(self):
        reader = FakeReader()
        tickets = [
            receive(corpus.message(message_id=f"<f{index}@x>", subject=f"Spam run {index}"), reader=reader)
            for index in range(4)
        ]

        self.assertEqual(len({ticket.pk for ticket in tickets[:2]}), 2)
        self.assertEqual(tickets[2].pk, tickets[1].pk)
        self.assertEqual(tickets[3].pk, tickets[1].pk)
        grouped = Ticket.objects.get(pk=tickets[1].pk)
        self.assertIn("flood", grouped.flags)
        self.assertEqual(grouped.messages.count(), 3)
        self.assertIn(Kind.FLOOD, event_kinds(grouped))

    def test_a_persons_message_is_never_grouped_into_a_closed_ticket(self):
        # Grouped into a closed ticket it would be hidden: it neither reopens it nor shows in the default queue.
        reader = FakeReader()
        first, latest = (
            receive(corpus.message(message_id=f"<c{index}@x>", subject=f"Run {index}"), reader=reader)
            for index in range(2)
        )
        Ticket.objects.filter(pk=latest.pk).update(status=Status.CLOSED, closed_at=timezone.now())

        grouped = receive(corpus.message(message_id="<c2@x>", subject="Run 2"), reader=reader)
        Ticket.objects.filter(pk=first.pk).update(status=Status.RESOLVED, closed_at=timezone.now())
        alone = receive(corpus.message(message_id="<c3@x>", subject="Run 3"), reader=reader)

        self.assertEqual(grouped.pk, first.pk)  # the latest open one
        self.assertNotIn(alone.pk, (first.pk, latest.pk, grouped.pk))  # none open: a ticket of its own
        self.assertEqual((alone.status, alone.unread), (Status.NEW, True))

    def test_automated_mail_is_never_grouped(self):
        reader = FakeReader()
        numbers = {
            receive(corpus.out_of_office(message_id=f"<o{index}@x>"), reader=reader).number for index in range(4)
        }

        self.assertEqual(len(numbers), 4)
