"""Helpdesk → Queue actions behind the typed confirmation (Mark as spam, Merge).

- The confirmation page names the tickets ("Marking as spam: I2G-#…", the first 20 and how many more); without the
  typed confirmation the action runs at once and nothing is announced.
- Cancel and the confirmed action go back to the view of the list the action was chosen on; a merge someone else
  made while the confirmation page was open is not made again.
"""

from django.test import override_settings
from django.urls import reverse

from ....models import Ticket, TicketEvent
from ....services import tickets
from ...helpers.service import Status, new_ticket
from .support import ACTION_SESSION_KEY, CHANGELIST, EVERYTHING, QueueCase, history

CONFIRM = "admin:helpdesk_ticket_confirm_action"


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class SpamConfirmationTests(QueueCase):
    def test_the_confirmation_page_names_the_tickets(self):
        first, second = new_ticket(subject="Win a prize"), new_ticket(subject="Claim it now")

        response = self.act("mark_spam", second, first)

        self.assertContains(response, f"Marking as spam: {first.display_number}, {second.display_number}.")
        self.assertEqual(response.context["action_name"], "mark_spam")
        self.assertEqual(Ticket.objects.filter(status=Status.SPAM).count(), 0)  # nothing until the word is typed

    def test_a_long_selection_names_the_first_twenty_and_counts_the_rest(self):
        chosen = [new_ticket(subject=f"Offer {index}") for index in range(22)]

        response = self.act("mark_spam", *reversed(chosen))

        numbers = ", ".join(ticket.display_number for ticket in chosen[:20])
        self.assertContains(response, f"Marking as spam: {numbers} and 2 more.")

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_without_the_typed_confirmation_it_runs_at_once(self):
        ticket = new_ticket(subject="Win a prize")

        response = self.act("mark_spam", ticket)

        self.assertEqual(self.messages(response), ["1 ticket marked as spam."])
        self.assertEqual(Ticket.objects.get(pk=ticket.pk).status, Status.SPAM)
        self.assertEqual(history(ticket), ["Marked as spam (bulk action)."])


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class WayBackTests(QueueCase):
    view = f"{EVERYTHING}&q=Parking"

    def setUp(self):
        super().setUp()
        self.older = new_ticket(subject="Parking")
        self.newer = new_ticket(subject="Parking again")
        self.list_url = f"{reverse(CHANGELIST)}{self.view}"

    def test_cancel_goes_back_to_the_view_of_the_list(self):
        page = self.act("merge_tickets", self.newer, self.older, view=self.view)

        self.assertEqual(self.client.session[ACTION_SESSION_KEY]["return_url"], self.list_url)
        self.assertEqual(page.context["cancel_url"], self.list_url)
        older, newer = self.older.display_number, self.newer.display_number
        self.assertContains(page, f"Merging {older}, {newer} into {older} (the oldest).")

    def confirm(self, **extra):
        token = self.client.session[ACTION_SESSION_KEY]["token"]
        return self.client.post(reverse(CONFIRM), {"confirmation_word": "MERGE", "token": token}, **extra)

    def test_the_confirmed_action_goes_back_to_it_too(self):
        self.act("merge_tickets", self.newer, self.older, view=self.view, follow=False)

        response = self.confirm()

        self.assertRedirects(response, self.list_url, fetch_redirect_response=False)
        self.newer.refresh_from_db()
        self.assertEqual((self.newer.status, self.newer.merged_into), (Status.MERGED, self.older))
        self.assertEqual(history(self.newer), [f"Merged into {self.older.display_number} (bulk action)."])

    def test_a_merge_someone_else_made_meanwhile_is_not_made_again(self):
        self.act("merge_tickets", self.newer, self.older, view=self.view, follow=False)
        tickets.merge([self.newer, self.older], actor=self.agent)  # meanwhile, from another tab
        merged = TicketEvent.objects.filter(kind=TicketEvent.Kind.MERGED).count()

        response = self.confirm(follow=True)

        self.assertEqual(self.messages(response)[-1], "Select at least two tickets that are not merged already.")
        self.assertEqual(TicketEvent.objects.filter(kind=TicketEvent.Kind.MERGED).count(), merged)
        self.assertRedirects(response, self.list_url)
