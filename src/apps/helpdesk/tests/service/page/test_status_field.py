"""The ticket page's Status.

- Never Merged (only a merge makes one) or Spam (the queue's "Mark as spam", behind its typed confirmation); New only
  while the ticket is New. A hidden status posted as an edit is refused; a page shown while the ticket was New still
  saves after the ticket left it.
- Read-only for automated mail and spam ("Not automated: move to the queue" brings those back), and a merged ticket's
  page is read-only altogether: no save buttons, and a post is refused.
"""

from ....models import Ticket, TicketEvent
from ...helpers.service import Status, new_ticket
from .support import PageCase, change_url

LATER = ["open", "pending_customer", "pending_internal", "resolved", "closed"]


class StatusChoiceTests(PageCase):
    def choices(self, ticket) -> list[str]:
        return [value for value, _label in self.form(self.page(ticket)).fields["status"].choices]

    def test_new_is_offered_only_while_the_ticket_is_new_and_merged_or_spam_never(self):
        self.assertEqual(self.choices(new_ticket()), ["new", *LATER])
        for status in LATER:
            with self.subTest(status):
                self.assertEqual(self.choices(new_ticket(status=status)), LATER)

    def test_a_hidden_status_posted_as_an_edit_is_refused(self):
        ticket = new_ticket(status=Status.OPEN)
        for status in (Status.NEW, Status.MERGED, Status.SPAM):
            with self.subTest(status):
                response = self.save(ticket, status=status, urgency="1")

                self.assertEqual(response.status_code, 200)
                errors = self.form(response).errors
                self.assertEqual(errors["status"], ["This status cannot be chosen on the ticket page."])
        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.urgency), (Status.OPEN, 2))
        self.assertFalse(ticket.events.exists())

    def test_a_value_that_is_no_status_at_all_is_an_invalid_choice(self):
        response = self.save(new_ticket(status=Status.OPEN), status="archived")

        self.assertIn("Select a valid choice.", str(self.form(response).errors["status"]))

    def test_a_page_shown_while_the_ticket_was_new_still_saves_after_it_left_new(self):
        ticket = new_ticket()
        shown = self.shown(ticket)  # Status: New, as it was then
        Ticket.objects.filter(pk=ticket.pk).update(status=Status.OPEN)  # someone moved it on meanwhile

        response = self.save(ticket, shown, urgency="1")

        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.urgency), (Status.OPEN, 1))


class ReadOnlyStatusTests(PageCase):
    def test_automated_mail_and_spam_keep_their_status_and_the_rest_still_saves(self):
        automated = new_ticket(automated=True, status=Status.CLOSED, classification="auto_reply")
        spam = new_ticket(status=Status.SPAM, classification="spam")
        for ticket in (automated, spam):
            with self.subTest(ticket.classification):
                shown = self.shown(ticket)
                self.assertNotIn("status", shown)

                response = self.client.post(change_url(ticket), {**shown, "status": Status.OPEN, "urgency": "1"})

                self.assertEqual(response.status_code, 302)
                current = Ticket.objects.get(pk=ticket.pk)
                self.assertEqual((current.status, current.urgency), (ticket.status, 1))

    def test_a_merged_tickets_page_is_read_only(self):
        target = new_ticket(status=Status.OPEN)
        merged = new_ticket(status=Status.MERGED, merged_into=target)
        open_page = self.page(target)

        page = self.page(merged)
        response = self.client.post(change_url(merged), {"status": Status.OPEN, "urgency": "1"})

        self.assertContains(open_page, 'name="_save"')
        self.assertEqual(list(self.form(page).fields), [])  # every field is shown read-only
        self.assertNotContains(page, 'name="_save"')
        self.assertNotContains(page, 'name="_continue"')
        self.assertContains(page, "This ticket was merged and is read-only")
        self.assertRedirects(response, change_url(merged), fetch_redirect_response=False)
        follow = self.client.get(response.url)
        self.assertContains(follow, f"{merged.display_number} was merged into {target.display_number} while you")
        merged.refresh_from_db()
        self.assertEqual((merged.status, merged.urgency), (Status.MERGED, 2))
        self.assertFalse(TicketEvent.objects.filter(ticket=merged).exists())
