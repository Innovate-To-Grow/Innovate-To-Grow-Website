"""What the ticket page explains: why Exchange's own rating made mail spam or bulk mail (with the threshold now on
Settings), Exchange's mark for mail from inside the organisation, why a backfilled ticket has no SLA, and the archive
warning's two choices, set apart."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from ....models import HelpdeskSettings, TicketAttachment, TicketMessage
from ... import corpus
from ...helpers import receive
from ...helpers.service import Status, clocked_ticket, new_ticket
from ..page.support import PageCase, ticket_admin

SPAM_WHY = "Why: Exchange rated it spam (SCL {}; spam from SCL {} on Settings)."
BULK_WHY = "Why: Exchange rated it bulk mail (BCL {}; bulk from BCL {} on Settings)."
HOUR = timedelta(hours=1)


class ExchangeRatingTests(PageCase):
    def test_spam_by_its_spam_confidence_level_says_so_with_the_threshold_in_effect(self):
        ticket = receive(corpus.spam(scl="6"))

        self.assertContains(self.page(ticket), SPAM_WHY.format(6, 5))
        HelpdeskSettings.objects.create(spam_scl_threshold=7)
        # Raised past its level since: the reason says so rather than contradict itself ("SCL 6; spam from SCL 7").
        page = self.page(ticket)
        self.assertNotContains(page, SPAM_WHY.format(6, 7))
        self.assertContains(
            page,
            "Why: Exchange rated it spam (SCL 6; spam at the threshold when it arrived; Settings now says from SCL 7).",
        )

    def test_bulk_mail_by_its_bulk_complaint_level_says_so(self):
        ticket = receive(corpus.message(message_id="<bcl@vendor.example>", headers={"X-Microsoft-Antispam": "BCL:8;"}))

        response = self.page(ticket)

        self.assertEqual(ticket.classification, "bulk")
        self.assertContains(response, BULK_WHY.format(8, 7))
        self.assertNotContains(response, "Exchange rated it spam")

    def test_exchanges_spam_filter_verdict_says_so(self):
        raw = corpus.message(message_id="<sfv@x.example>", headers={"X-Forefront-Antispam-Report": "SFV:SPM;"})

        self.assertContains(self.page(receive(raw)), "Why: Exchange's spam filter marked it as spam.")

    def test_mail_decided_otherwise_gives_no_exchange_reason(self):
        listed = receive(corpus.message(message_id="<list@x.example>", headers={"List-Id": "<news.x.example>"}))
        low = receive(corpus.message(message_id="<low@x.example>", headers={"X-Microsoft-Antispam": "BCL:3;"}))

        for ticket in (listed, low):
            with self.subTest(ticket.subject):
                self.assertNotContains(self.page(ticket), "Why: Exchange")
        self.assertEqual((listed.classification, low.automated), ("bulk", False))

    def test_the_authentication_line_shows_exchanges_internal_mark(self):
        ticket = new_ticket(status=Status.OPEN)
        TicketMessage.objects.create(
            ticket=ticket,
            kind=TicketMessage.Kind.CUSTOMER,
            occurred_at=timezone.now(),
            from_address="dean@example.edu",
            body_text="See you at the showcase.",
            auth_summary={"spf": "pass", "authas": "internal"},  # PostgreSQL may list jsonb keys in another order
        )

        response = self.page(ticket)

        self.assertContains(response, "Exchange: internal")
        self.assertContains(response, "SPF pass")
        self.assertNotContains(response, "AUTHAS")


class BackfilledSLATests(PageCase):
    def sla(self, ticket) -> tuple[str, str]:
        """The SLA panel's two rows (first response, resolution) as the page shows them."""
        page = ticket_admin()
        return str(page.sla_response_display(ticket)), str(page.sla_resolution_display(ticket))

    def test_a_backfilled_ticket_says_why_it_has_no_sla(self):
        ticket = receive(corpus.message(), received=timezone.now() - 48 * HOUR - 2 * timedelta(minutes=1))

        self.assertTrue(ticket.backfilled)
        response = self.page(ticket)
        self.assertContains(response, "No SLA (backfilled: imported 48 h after it arrived)", count=2)

    def test_a_long_delay_is_counted_in_days(self):
        ticket = receive(corpus.message(), received=timezone.now() - timedelta(days=5, hours=2))

        self.assertEqual(self.sla(ticket)[0], "No SLA (backfilled: imported 5 days after it arrived)")

    def test_tickets_without_a_clock_for_another_reason_say_only_no_sla(self):
        old = new_ticket(status=Status.OPEN)  # from before the SLA
        # Automated mail never has a clock (moving it to the queue starts one, backfilled or not).
        automated = new_ticket(
            status=Status.CLOSED, automated=True, backfilled=True, first_message_at=timezone.now() - 30 * HOUR
        )

        for ticket in (old, automated):
            with self.subTest(ticket.pk):
                self.assertEqual(self.sla(ticket), ("No SLA", "No SLA"))

    def test_a_ticket_with_a_clock_shows_the_clock(self):
        ticket = clocked_ticket(status=Status.OPEN)

        self.assertNotIn("No SLA", self.sla(ticket)[0])


class ArchiveWarningTests(PageCase):
    def test_download_anyway_and_back_sit_apart(self):
        raw = corpus.message(attachments=[("bundle.zip", b"PK\x03\x04archive", "application/zip")])
        ticket = receive(raw)
        attachment = TicketAttachment.objects.get(message__ticket=ticket, filename="bundle.zip")

        response = self.client.get(reverse("admin:helpdesk_ticket_attachment", args=[ticket.pk, attachment.pk]))

        page = response.content.decode()
        row = page[page.index('<p class="flex flex-wrap items-center gap-4">') :]
        self.assertLess(row.index("Download anyway"), row.index(f"Back to {ticket.display_number}"))
        self.assertLess(row.index(f"Back to {ticket.display_number}"), row.index("</p>"))
