"""A merged ticket takes no internal note: its messages and work are on the ticket it was merged into.

- A note posted to a merged ticket (a page opened before the merge) is refused with a message naming that ticket, and
  the page goes there; nothing is stored on either ticket. A merged ticket whose target is gone says only that it was
  merged, and stays on its own page.
- The merged ticket's page shows no note form, only where to work instead.
"""

from django.urls import reverse

from ....models import Ticket, TicketMessage
from ...helpers.service import Status, new_ticket
from .support import PageCase, change_url

NOTE = TicketMessage.Kind.NOTE


class MergedTicketNoteTests(PageCase):
    def setUp(self):
        super().setUp()
        self.target = new_ticket(subject="Parking", status=Status.OPEN)
        self.merged = new_ticket(subject="Parking again", status=Status.MERGED, merged_into=self.target)

    def note(self, ticket, body="Called the requester back."):
        return self.client.post(reverse("admin:helpdesk_ticket_note", args=[ticket.pk]), {"body": body})

    def test_a_note_posted_to_a_merged_ticket_is_refused_and_goes_to_the_target(self):
        response = self.note(self.merged)

        self.assertRedirects(response, change_url(self.target), fetch_redirect_response=False)
        merged, target = self.merged.display_number, self.target.display_number
        self.assertEqual(
            self.messages(response), [f"{merged} was merged into {target}: add the note there. Nothing was added."]
        )
        self.assertFalse(TicketMessage.objects.filter(kind=NOTE).exists())
        self.assertFalse(self.merged.events.exists())
        self.assertFalse(self.target.events.exists())

    def test_a_merged_ticket_whose_target_is_gone_stays_on_its_own_page(self):
        Ticket.objects.filter(pk=self.merged.pk).update(merged_into=None)

        response = self.note(self.merged)

        self.assertRedirects(response, change_url(self.merged), fetch_redirect_response=False)
        self.assertEqual(self.messages(response), [f"{self.merged.display_number} was merged. Nothing was added."])
        self.assertFalse(TicketMessage.objects.filter(kind=NOTE).exists())

    def test_the_merged_tickets_page_shows_no_note_form(self):
        note_url = reverse("admin:helpdesk_ticket_note", args=[self.merged.pk])

        page = self.page(self.merged)
        target_page = self.page(self.target)

        self.assertNotContains(page, 'id="helpdesk-note-body"')
        self.assertNotContains(page, f'action="{note_url}"')
        self.assertNotContains(page, "Add an internal note")
        link = f'<a href="{change_url(self.target)}">{self.target.display_number}</a>'
        instead = f"This ticket was merged and is read-only: work on {link}."
        self.assertContains(page, f'<p class="i2g-helpdesk-muted" id="helpdesk-note">{instead}</p>', html=True)
        self.assertContains(target_page, 'id="helpdesk-note-body"')
