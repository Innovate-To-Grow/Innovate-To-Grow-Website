from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.helpdesk.tests.tickets.test_tickets import Kind, Status, new_ticket

from ...models import TicketCategory, TicketMessage
from ...services import tickets
from .. import corpus
from ..helpers import FakeReader, helpdesk_staff, receive


class StaffActionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.ticket = new_ticket(participants=["pat@example.org"])

    def kinds(self, ticket=None):
        return list((ticket or self.ticket).events.order_by("created_at").values_list("kind", flat=True))

    def test_each_field_change_is_recorded_once(self):
        category = TicketCategory.objects.create(name="Registration")

        changed = tickets.update_ticket(
            self.ticket,
            actor=self.agent,
            status=Status.RESOLVED,
            priority="high",
            category=category,
            assignee=self.agent,  # deprecated (tickets have no owner): ignored
        )
        unchanged = tickets.update_ticket(self.ticket, actor=self.agent, status=Status.RESOLVED, priority="high")

        self.ticket.refresh_from_db()
        self.assertEqual(changed, ["status", "priority", "category"])
        self.assertEqual(unchanged, [])
        self.assertEqual(
            (self.ticket.status, self.ticket.priority, self.ticket.category, self.ticket.assignee),
            (Status.RESOLVED, "high", category, None),
        )
        self.assertIsNotNone(self.ticket.closed_at)
        self.assertIsNotNone(self.ticket.resolved_at)
        # Leaving New is the first response (SLA), recorded after the changes that made it.
        self.assertEqual(self.kinds(), [Kind.STATUS, Kind.PRIORITY, Kind.CATEGORY, Kind.RESPONDED])
        # Every change is on record with who made it.
        self.assertEqual(set(self.ticket.events.values_list("actor", flat=True)), {self.agent.pk})

    def test_reopening_clears_the_close_times(self):
        tickets.update_ticket(self.ticket, actor=self.agent, status=Status.CLOSED)
        tickets.update_ticket(self.ticket, actor=self.agent, status=Status.OPEN)

        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.closed_at, self.ticket.resolved_at), (None, None))

    def test_a_note_is_internal_scrubbed_and_recorded(self):
        note = tickets.add_note(self.ticket, actor=self.agent, body=f"  Called them. Link: {corpus.LOGIN_LINK}  ")

        self.assertEqual((note.kind, note.author, note.from_name), (TicketMessage.Kind.NOTE, self.agent, "Avery Agent"))
        self.assertEqual(note.body_text, "Called them. Link: [sign-in link removed]")
        self.assertEqual(self.kinds(), [Kind.NOTE])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.last_activity_at, note.occurred_at)

    def test_a_pasted_nul_character_is_dropped_instead_of_failing_the_save(self):
        note = tickets.add_note(self.ticket, actor=self.agent, body="Called\x00 them.")

        note.refresh_from_db()
        self.assertEqual(note.body_text, "Called them.")

    def test_bulk_status_and_read(self):
        other = new_ticket(unread=True)

        self.assertEqual(tickets.set_status([self.ticket, other], Status.CLOSED, actor=self.agent), 2)
        self.assertEqual(tickets.mark_read([self.ticket, other]), 1)
        other.refresh_from_db()
        self.assertFalse(other.unread)
        self.assertEqual(tickets.mark_unread([self.ticket, other]), 2)

    def test_spam_and_moving_automated_mail_to_the_queue(self):
        automated = new_ticket(
            automated=True, status=Status.CLOSED, classification="auto_reply", closed_at=timezone.now()
        )
        merged = new_ticket(status=Status.MERGED)

        self.assertEqual(tickets.mark_spam([self.ticket, merged], actor=self.agent), 1)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Status.SPAM)
        self.assertEqual(self.kinds()[-1], Kind.SPAM)

        self.assertEqual(tickets.move_to_queue([automated, self.ticket, merged], actor=self.agent), 2)
        automated.refresh_from_db()
        self.ticket.refresh_from_db()
        # Nobody answered either yet: New again, so moving it on is still its first response.
        self.assertEqual(
            (automated.automated, automated.status, automated.closed_at, automated.unread),
            (False, Status.NEW, None, True),
        )
        self.assertEqual((self.ticket.status, self.ticket.unread), (Status.NEW, True))
        self.assertEqual(automated.events.get(kind=Kind.RECLASSIFIED).data, {"from": "auto_reply", "to": "human"})

    def test_merging_moves_everything_into_the_oldest_ticket(self):
        reader = FakeReader()
        first = receive(corpus.message(message_id="<a@x>"), reader=reader)
        second = receive(corpus.message(message_id="<b@x>", sender="kim@example.org"), reader=reader)
        tickets.add_note(second, actor=self.agent, body="note")

        target = tickets.merge([second, first], actor=self.agent)

        second.refresh_from_db()
        self.assertEqual(target.pk, first.pk)
        self.assertEqual(target.messages.count(), 3)
        self.assertEqual((second.status, second.merged_into), (Status.MERGED, first))
        self.assertIsNotNone(second.closed_at)
        first.refresh_from_db()
        self.assertEqual(set(first.participants), {"pat@example.org", "kim@example.org"})
        self.assertEqual(first.events.get(kind=Kind.MERGED).data, {"source": second.number, "messages": 2})
        self.assertEqual(second.events.get(kind=Kind.MERGED).data, {"into": first.number})
        self.assertIsNone(tickets.merge([first], actor=self.agent))
        self.assertIsNone(tickets.merge([first, second], actor=self.agent))
