"""The ticket page's own "Not automated: move to the queue", beside Save: the queue action's move and messages for the
ticket on the page, offered only on automated mail or spam that is not merged, with no typed confirmation."""

from django.contrib.admin.models import LogEntry
from django.test import override_settings

from ....models import TicketEvent
from ....services import tickets
from ...helpers.service import Status, new_ticket
from ..page.support import PageCase, change_url

BUTTON = "helpdesk_ticket_move_to_queue_here"


def automated(**values):
    """List mail as the ingest stores it: closed at once, hidden, low priority (3 × 3)."""
    values = {"subject": "Re: our newsletter", "status": Status.CLOSED, "classification": "bulk", **values}
    return new_ticket(automated=True, impact=3, urgency=3, priority="low", **values)


class PageMoveTests(PageCase):
    def move(self, ticket, **edits):
        return self.save(ticket, **edits, **{BUTTON: ""})

    def test_automated_mail_offers_the_move_beside_save_under_the_name_its_classification_gives(self):
        page = self.page(automated()).content.decode()

        save = page.index('name="_save"')
        button = page.index(f'name="{BUTTON}"', save)  # in the row of Save buttons, after Save
        self.assertIn(tickets.MOVE_TO_QUEUE, page[button : page.index("</button>", button)])
        where = "beside Save at the bottom of this page."
        self.assertIn(f"If a person wrote it, use &quot;{tickets.MOVE_TO_QUEUE}&quot; {where}", page)

    def test_the_button_moves_the_ticket_and_comes_back_to_its_page(self):
        ticket = automated()

        response = self.move(ticket)

        self.assertRedirects(response, change_url(ticket), fetch_redirect_response=False)
        self.assertEqual(self.messages(response), ["1 ticket moved to the queue."])
        ticket.refresh_from_db()
        self.assertEqual((ticket.automated, ticket.status, ticket.unread), (False, Status.NEW, True))
        self.assertEqual((ticket.impact, ticket.urgency), (2, 2))  # a person's message starts where any other does
        self.assertIsNotNone(ticket.sla_started_at)
        self.assertTrue(ticket.events.filter(kind=TicketEvent.Kind.RECLASSIFIED, actor=self.agent).exists())
        entry = LogEntry.objects.get(object_id=str(ticket.pk))
        self.assertEqual(entry.change_message, "Moved to the queue: not automated.")

    def test_after_the_move_the_page_offers_it_no_more(self):
        ticket = automated()
        self.move(ticket)

        response = self.page(ticket)

        self.assertNotContains(response, f'name="{BUTTON}"')
        self.assertNotContains(response, "hidden from the default queue")

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_no_typed_confirmation_is_asked(self):
        ticket = automated()

        response = self.move(ticket)

        self.assertRedirects(response, change_url(ticket), fetch_redirect_response=False)
        ticket.refresh_from_db()
        self.assertFalse(ticket.automated)

    def test_what_was_edited_on_the_page_is_saved_with_it(self):
        ticket = automated()

        self.move(ticket, impact="1")

        ticket.refresh_from_db()
        # The edit is kept: only automated mail's own 3 × 3 starts again at 2 × 2.
        self.assertEqual((ticket.automated, ticket.impact, ticket.urgency), (False, 1, 3))
        changes = set(LogEntry.objects.filter(object_id=str(ticket.pk)).values_list("change_message", flat=True))
        self.assertEqual(changes, {"Changed impact, priority.", "Moved to the queue: not automated."})

    def test_spam_marked_by_staff_is_offered_it_too(self):
        ticket = new_ticket(status=Status.SPAM, classification="human")

        self.assertContains(self.page(ticket), f'name="{BUTTON}"')
        self.move(ticket)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Status.NEW)

    def test_a_persons_ticket_offers_no_move_and_a_posted_one_leaves_it_as_it_was(self):
        ticket = new_ticket(status=Status.OPEN)

        page = self.page(ticket)
        response = self.move(ticket)

        self.assertNotContains(page, f'name="{BUTTON}"')
        self.assertRedirects(response, change_url(ticket), fetch_redirect_response=False)
        self.assertEqual(
            self.messages(response),
            [
                "0 tickets moved to the queue. 1 left as it was: only automated mail and spam are moved (a merged "
                "ticket never)."
            ],
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Status.OPEN)
        self.assertFalse(LogEntry.objects.filter(change_message__startswith="Moved").exists())

    def test_merged_automated_mail_offers_no_move_and_says_why(self):
        target = new_ticket(status=Status.OPEN)
        ticket = automated(status=Status.MERGED, merged_into=target)

        response = self.page(ticket)

        self.assertNotContains(response, f'name="{BUTTON}"')
        self.assertContains(response, "it was merged, so it stays as it is.")

    def test_a_ticket_merged_while_the_page_was_open_is_not_moved(self):
        person, ticket = new_ticket(status=Status.OPEN), automated()  # the oldest is the person's: it takes the merge
        shown = self.shown(ticket)
        tickets.merge([person, ticket], actor=self.agent)

        response = self.client.post(change_url(ticket), {**shown, BUTTON: ""})

        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.automated), (Status.MERGED, True))
        self.assertIn("nothing was saved", self.messages(response)[0])

    def test_a_malformed_ticket_address_still_answers_as_before(self):
        response = self.client.get("/admin/helpdesk/ticket/not-a-uuid/change/")

        self.assertEqual(response.status_code, 302)  # Django's "does not exist" redirect, not an error
