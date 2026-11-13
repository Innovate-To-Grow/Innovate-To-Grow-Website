"""Bounce categories on the Email Monitoring pages: the Bounce Reports column, filter, sort, search and legend; the
overview's top reasons; the Bounced addresses column, filter, counts, suggestions and guidance; the rebuild page."""

from datetime import timedelta

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from apps.core.models import EmailBounce
from apps.core.tests.services.email_monitoring.helpers import make_bounce
from apps.event.tests.helpers import make_superuser
from apps.mail.models import BouncedAddress
from apps.mail.tests.services.bounced_addresses.helpers import make_row, settled

BOUNCES = "admin:mail_email_monitoring_bounces"
OVERVIEW = "admin:mail_email_monitoring"
LIST = "admin:mail_email_monitoring_addresses"
DETAIL = "admin:mail_email_monitoring_address"
REBUILD = "admin:mail_email_monitoring_addresses_rebuild"
RELAY_ROW = {
    "hard_count": 0,
    "rejected_count": 1,
    "category_counts": {"relay_denied": 1},
    "last_category": "relay_denied",
}


class BounceReportCategoryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())
        now = timezone.now()
        make_bounce(
            recipient="relay@example.org",
            category="relay_denied",
            classification="rejected",
            status_code="5.7.1",
            smtp_code="554",
            diagnostic_code="554 5.7.1 <relay@example.org>: Relay access denied",
            received_at=now,
        )
        make_bounce(
            recipient="slow@example.org",
            category="transient",
            classification="soft",
            status_code="5.4.316",
            received_at=now - timedelta(minutes=1),
        )
        make_bounce(recipient="old@example.org", category="", received_at=now - timedelta(minutes=2))

    def recipients(self, **params):
        response = self.client.get(reverse(BOUNCES), params)
        return [bounce.recipient for bounce in response.context["page"].object_list]

    def test_each_report_shows_its_category_and_what_it_means(self):
        response = self.client.get(reverse(BOUNCES))

        self.assertContains(response, "<strong>Relay denied</strong>", html=True)
        self.assertContains(response, "Rejected · Our sending side: sending route or authorisation")
        self.assertContains(response, "Soft bounce · Temporary: the address is probably fine")
        self.assertContains(response, "Not classified yet")
        self.assertContains(response, "554 5.7.1")
        self.assertContains(response, "What the categories mean")
        for item in EmailBounce.category_legend():
            self.assertContains(response, escape(item["guidance"]))
        self.assertContains(response, '<option value="relay_denied">Relay denied</option>', html=True)

    def test_the_category_filter_sort_and_search(self):
        self.assertEqual(self.recipients(category="relay_denied"), ["relay@example.org"])
        self.assertEqual(len(self.recipients(category="bogus")), 3)
        self.assertEqual(self.recipients(q="Relay access"), ["relay@example.org"])
        self.assertEqual(self.recipients(q="554"), ["relay@example.org"])
        self.assertEqual(
            self.recipients(sort="category", dir="asc"), ["old@example.org", "relay@example.org", "slow@example.org"]
        )
        response = self.client.get(reverse(BOUNCES), {"category": "transient"})
        self.assertContains(response, "category=transient")

    def test_the_overview_labels_its_top_bounce_reasons_by_category(self):
        response = self.client.get(reverse(OVERVIEW))

        self.assertContains(response, "Bounce category")
        labels = {row["label"] for row in response.context["bounce_reasons"]}
        self.assertEqual(labels, {"Relay denied", "Temporary failure", "Not classified yet"})


class AddressCategoryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(make_superuser())

    def test_the_list_shows_the_last_category_the_counts_and_filters_by_category(self):
        make_row("relay@example.org", **RELAY_ROW)
        make_row("gone@example.org")

        with settled():
            response = self.client.get(reverse(LIST))
            relay_only = self.client.get(reverse(LIST), {"category": "relay_denied"})

        self.assertContains(response, "relay denied 1")
        self.assertContains(response, "not found 1")
        self.assertContains(response, "Our sending side: sending route or authorisation")
        self.assertContains(response, Suggestion.RELAY.label)
        self.assertContains(response, "What the categories mean")
        self.assertContains(response, '<option value="relay_denied">Relay denied</option>', html=True)
        self.assertEqual([entry["row"].address for entry in relay_only.context["entries"]], ["relay@example.org"])

    def test_only_a_suggestion_about_the_address_asks_to_check_unmatched_reports(self):
        make_row("relay@example.org", **RELAY_ROW)

        with settled():
            sender_side = self.client.get(reverse(LIST))
        make_row("gone@example.org")
        with settled():
            address = self.client.get(reverse(LIST))

        self.assertNotContains(sender_side, "unmatched reports only: check them first")
        self.assertContains(address, "unmatched reports only: check them first", count=1)

    def test_the_latest_ses_event_shows_instead_of_a_category(self):
        now = timezone.now()
        make_row(
            "ses@example.org",
            ses_permanent_count=1,
            ses_last_at=now + timedelta(minutes=5),
            ses_last={"event": "bounce", "type": "Permanent", "subtype": "General"},
        )

        with settled():
            response = self.client.get(reverse(LIST))

        self.assertContains(response, "SES bounce<br>", html=False)
        self.assertContains(response, "SES permanent 1")

    def test_the_address_page_explains_the_last_category(self):
        row = make_row(
            "disabled@example.org",
            category_counts={"mailbox_disabled": 1},
            last_category="mailbox_disabled",
            last_status_code="5.2.1",
            suggestion=BouncedAddress.Suggestion.REPLACE,
        )

        response = self.client.get(reverse(DETAIL, args=[row.pk]))

        self.assertContains(response, "Last category")
        self.assertContains(response, "The mailbox is disabled. Strong evidence")
        self.assertContains(response, "mailbox disabled 1")
        self.assertContains(response, BouncedAddress.Suggestion.REPLACE.label)
        self.assertContains(response, "What the categories mean")

    def test_a_row_counted_before_categories_still_shows_its_counts(self):
        row = make_row("legacy@example.org", category_counts={}, last_category="")

        with settled():
            listing = self.client.get(reverse(LIST))
        detail = self.client.get(reverse(DETAIL, args=[row.pk]))

        self.assertContains(listing, "hard 1")
        self.assertContains(detail, "hard 1 · soft 0 · rejected 0 · delayed 0 · unknown 0")

    def test_the_rebuild_page_says_the_reports_are_classified_again(self):
        make_bounce(recipient="r@example.org", status_code="5.0.0", diagnostic_code="550 5.0.0 Connection timed out")

        confirm = self.client.post(reverse(REBUILD))
        with settled():
            applied = self.client.post(reverse(REBUILD), {"step": "apply"})

        self.assertContains(confirm, "classified again with the current rules")
        notes = [str(message) for message in get_messages(applied.wsgi_request)]
        self.assertTrue(any("classified again with the current rules (1 changed)" in note for note in notes))
        self.assertEqual(BouncedAddress.objects.get(address="r@example.org").category_counts, {"transient": 1})


Suggestion = BouncedAddress.Suggestion
