"""The pages after the fourth live check of the admin:

- Retry from Ingest Problems' Dismissed view queues the message again (the view's own filter used to lose it as its
  dismissal went, so nothing was queued);
- a ticket page shown while the ticket was automated mail or spam (Status read-only, so not posted) saves without
  "This field is required." once someone has moved the ticket to the queue: a field the page did not show is not
  edited by its save, and its move button says who moved the ticket already and that the edits were saved (not "0
  tickets moved", which reads like a failure);
- a backfilled ticket moved to the queue says its SLA ran from the move."""

from django.contrib.admin.models import LogEntry
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import InboundMessage

from ....models import TicketCategory
from ....services import tickets
from ...helpers import helpdesk_staff, make_admin, queue
from ...helpers.service import Status
from ..page.support import PageCase, change_url
from .test_page_move_to_queue import BUTTON, automated

Inbound = InboundMessage.Status


class RetryFromDismissedTests(TestCase):
    def test_retry_from_the_dismissed_view_queues_the_message_again(self):
        cache.clear()
        self.client.force_login(helpdesk_staff())
        gone = queue(status=Inbound.SKIPPED, last_error="No longer in the mailbox.")
        url = reverse("admin:helpdesk_ingestrecord_changelist")
        chosen = {"index": "0", "_selected_action": [str(gone.pk)]}
        self.client.post(f"{url}?state=all", {"action": "dismiss", **chosen})

        response = self.client.post(f"{url}?state=dismissed", {"action": "retry", **chosen}, follow=True)

        self.assertContains(response, "1 message queued again for import.")
        gone.refresh_from_db()
        self.assertEqual(gone.status, Inbound.PENDING)
        self.assertNotIn("dismissed", gone.result)


class StalePageTests(PageCase):
    def test_a_page_shown_before_the_ticket_was_moved_saves_without_an_error(self):
        ticket = automated()
        shown = self.shown(ticket)
        self.assertNotIn("status", shown)  # read-only on automated mail
        tickets.move_to_queue([ticket], actor=helpdesk_staff(email="blake@example.com"))

        for extra in ({}, {BUTTON: ""}):
            with self.subTest(extra):
                response = self.client.post(change_url(ticket), {**shown, **extra})

                self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.automated), (Status.NEW, False))

    def test_its_move_button_says_who_moved_it_meanwhile_and_that_the_edits_were_saved(self):
        ticket, events = automated(), TicketCategory.objects.create(name="Events")
        shown = self.shown(ticket)
        blake = make_admin(email="blake@example.com", first_name="Blake", last_name="Agent")
        tickets.move_to_queue([ticket], actor=blake)

        response = self.client.post(change_url(ticket), {**shown, "category": str(events.pk), BUTTON: ""})

        said = [(message.level_tag, str(message)) for message in get_messages(response.wsgi_request)]
        moved = f"{ticket.display_number} was moved to the queue already (by Blake Agent); your changes were saved."
        self.assertEqual(said, [("info", moved)])
        ticket.refresh_from_db()
        self.assertEqual(ticket.category, events)
        self.assertEqual(
            list(LogEntry.objects.filter(object_id=str(ticket.pk)).values_list("change_message", flat=True)),
            ["Changed category."],  # its own save only: the move was Blake's
        )


class BackfilledFlagTests(PageCase):
    def test_a_backfilled_ticket_moved_to_the_queue_says_its_sla_ran_from_the_move(self):
        ticket = automated(backfilled=True)
        before = self.page(ticket)

        tickets.move_to_queue([ticket], actor=self.agent)

        self.assertContains(before, "backfilled (imported late: no SLA and no acknowledgement)")
        self.assertContains(
            self.page(ticket), "backfilled (imported late: no acknowledgement; SLA from its move to the queue)"
        )
