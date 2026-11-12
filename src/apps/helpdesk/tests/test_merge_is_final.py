"""A merge is final: a merged ticket keeps its status, and only ``merge`` makes a ticket merged.

Otherwise ``merged_into`` falls out of step with the status: a closed and then reopened merged ticket came back to the
queue empty (its messages are on the ticket it was merged into, and so is its later mail), and "Merged" picked on the
ticket page hid a ticket that was merged into nothing. Held by the service (``update_ticket``, ``mark_spam``,
``move_to_queue``, each judging the row itself) and by the ticket page.
"""

from django.contrib.admin import helpers
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from ..models import Ticket, TicketEvent
from ..services import tickets
from .helpers import helpdesk_staff
from .test_merge import BOUNCE_SENDER, CHANGELIST, EVERYTHING, make_ticket, snapshot

Status = Ticket.Status
Kind = TicketEvent.Kind


class _MergedCase(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.target = make_ticket("Parking", hours_ago=5)
        self.merged = make_ticket("Parking again", requester="kim@example.org")
        tickets.merge([self.merged, self.target], actor=self.agent)
        self.merged.refresh_from_db()


class MergeIsFinalServiceTests(_MergedCase):
    def test_no_status_change_un_merges_a_ticket(self):
        before = snapshot()

        for status in Status.values:
            with self.subTest(status):
                self.assertEqual(tickets.update_ticket(self.merged, actor=self.agent, status=status), [])
        self.assertEqual(tickets.set_status([self.merged], Status.CLOSED, actor=self.agent), 0)
        self.assertEqual(tickets.set_status([self.merged], Status.OPEN, actor=self.agent), 0)
        self.assertEqual(tickets.mark_spam([self.merged], actor=self.agent), 0)

        self.assertEqual(snapshot(), before)

    def test_the_other_fields_of_a_merged_ticket_still_change(self):
        changed = tickets.update_ticket(self.merged, actor=self.agent, status=Status.OPEN, priority="high")

        self.merged.refresh_from_db()
        self.assertEqual(changed, ["priority"])
        self.assertEqual(
            (self.merged.status, self.merged.priority, self.merged.merged_into), (Status.MERGED, "high", self.target)
        )
        self.assertFalse(self.merged.events.filter(kind=Kind.STATUS).exists())

    def test_only_merge_makes_a_ticket_merged(self):
        other = make_ticket("Unrelated", requester="lee@example.org")
        before = snapshot()

        self.assertEqual(tickets.update_ticket(other, actor=self.agent, status=Status.MERGED), [])
        self.assertEqual(tickets.set_status([other], Status.MERGED, actor=self.agent), 0)

        self.assertEqual(snapshot(), before)

    def test_a_ticket_merged_since_the_list_was_shown_is_neither_marked_spam_nor_moved_to_the_queue(self):
        person = make_ticket("Question", requester="ana@example.org", hours_ago=9)
        bounce = make_ticket("Undeliverable", requester=BOUNCE_SENDER, automated=True, hours_ago=2)
        again = make_ticket("Question again", requester="ana@example.org", hours_ago=1)
        shown = {ticket.pk: Ticket.objects.get(pk=ticket.pk) for ticket in (bounce, again)}  # as the list showed them
        tickets.merge([person, bounce, again], actor=self.agent)  # meanwhile, by someone else
        before = snapshot()

        self.assertEqual(tickets.move_to_queue([shown[bounce.pk]], actor=self.agent), 0)
        self.assertEqual(tickets.mark_spam([shown[again.pk]], actor=self.agent), 0)

        self.assertEqual(snapshot(), before)
        self.assertEqual(
            set(Ticket.objects.filter(pk__in=shown).values_list("status", "merged_into")),
            {(Status.MERGED, person.pk)},
        )

    def test_a_ticket_moved_to_the_queue_meanwhile_is_not_moved_twice(self):
        bounce = make_ticket("Undeliverable", requester=BOUNCE_SENDER, automated=True)
        shown = Ticket.objects.get(pk=bounce.pk)

        self.assertEqual(tickets.move_to_queue([bounce], actor=self.agent), 1)
        self.assertEqual(tickets.move_to_queue([shown], actor=self.agent), 0)

        self.assertEqual(bounce.events.filter(kind=Kind.RECLASSIFIED).count(), 1)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class MergeIsFinalAdminTests(_MergedCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.agent)

    def act(self, action, *selected):
        data = {
            "action": action,
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(ticket.pk) for ticket in selected],
        }
        return self.client.post(f"{reverse(CHANGELIST)}{EVERYTHING}", data, follow=True)

    def test_close_then_reopen_leaves_a_merged_ticket_merged_and_out_of_the_queue(self):
        before = snapshot()

        closed = self.act("close_tickets", self.merged)
        reopened = self.act("reopen_tickets", self.merged)

        self.assertEqual([str(message) for message in get_messages(closed.wsgi_request)], ["0 tickets closed."])
        self.assertEqual([str(message) for message in get_messages(reopened.wsgi_request)], ["0 tickets reopened."])
        self.assertEqual(snapshot(), before)
        queue = self.client.get(reverse(CHANGELIST)).context["cl"].result_list
        self.assertEqual({ticket.subject for ticket in queue}, {"Parking"})

    def test_a_merged_tickets_status_is_read_only_on_its_page(self):
        url = reverse("admin:helpdesk_ticket_change", args=[self.merged.pk])
        page = self.client.get(url)
        before = snapshot()

        response = self.client.post(url, {"status": Status.OPEN, "priority": "normal", "category": "", "assignee": ""})

        self.assertNotIn("status", page.context["adminform"].form.fields)
        self.assertContains(page, "Merged")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(snapshot(), before)

    def test_merged_is_not_offered_on_a_tickets_page_and_a_posted_one_is_refused(self):
        other = make_ticket("Unrelated", requester="lee@example.org")
        url = reverse("admin:helpdesk_ticket_change", args=[other.pk])
        page = self.client.get(url)
        before = snapshot()

        response = self.client.post(
            url, {"status": Status.MERGED, "priority": "normal", "category": "", "assignee": ""}
        )

        choices = [value for value, _label in page.context["adminform"].form.fields["status"].choices]
        self.assertEqual(choices, [status for status in Status.values if status != Status.MERGED])
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.context["adminform"].form.errors)
        self.assertEqual(snapshot(), before)
