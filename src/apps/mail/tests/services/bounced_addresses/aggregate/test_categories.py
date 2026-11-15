"""Bounced addresses by bounce category: counting per category, the one recount after the upgrade, the rebuild that
classifies stored reports again, the category filter and sort, the audit text and the export, and mail.0026 (which
parks the Graph cursor so the previous release counts nothing while the deploy rolls out)."""

import importlib

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailBounce
from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressAction
from apps.mail.services.email_monitoring.addresses import aggregate

from ..helpers import count_now, make_bounce, make_row

Category = EmailBounce.Category
Suggestion = BouncedAddress.Suggestion
TIMEOUT = "550 5.0.0 connect to mail.example.net[203.0.113.25]:25: Connection timed out"
GMAIL_RECEIVING_RATE = (
    "550-5.2.1 The user you are trying to contact is receiving mail at a rate that prevents additional messages from "
    "being delivered. For more information, go to https://support.google.com/mail/?p=ReceivingRatePerm - gsmtp"
)
parking_migration = importlib.import_module("apps.mail.migrations.0026_bounced_address_categories")


def row_for(address: str) -> BouncedAddress:
    return BouncedAddress.objects.get(address=address)


class CategoryCountingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_reports_are_counted_by_category_and_the_latest_gives_the_last_category(self):
        now = timezone.now()
        make_bounce(recipient="c@example.org", category="transient", classification="soft", received_at=now)
        make_bounce(recipient="c@example.org", category="transient", classification="soft", received_at=now)
        make_bounce(recipient="c@example.org", category="relay_denied", classification="rejected", received_at=now)
        make_bounce(
            recipient="C@example.org",
            category="mailbox_disabled",
            status_code="5.2.1",
            received_at=now + timezone.timedelta(minutes=1),
        )

        count_now()

        row = row_for("c@example.org")
        self.assertEqual(row.category_counts, {"transient": 2, "relay_denied": 1, "mailbox_disabled": 1})
        self.assertEqual((row.hard_count, row.soft_count, row.rejected_count), (1, 2, 1))
        self.assertEqual((row.last_category, row.last_category_label), ("mailbox_disabled", "Mailbox disabled"))
        self.assertIn("Strong evidence", row.last_category_guidance)
        self.assertEqual(row.last_category_hint, "Evidence against the address")
        self.assertEqual(
            [(item["label"], item["count"]) for item in row.category_items],
            [("disabled", 1), ("temporary", 2), ("relay denied", 1)],
        )
        self.assertEqual(row.suggestion, Suggestion.REPLACE)

    def test_a_timeout_alone_never_suggests_marking_the_address_undeliverable(self):
        make_bounce(
            recipient="t@example.org", category="", classification="hard", status_code="5.0.0", diagnostic_code=TIMEOUT
        )

        count_now()

        row = row_for("t@example.org")
        self.assertEqual((row.category_counts, row.hard_count, row.soft_count), ({"transient": 1}, 0, 1))
        self.assertEqual(row.suggestion, "")

    def test_a_gmail_receiving_rate_limit_neither_suggests_replacing_the_address_nor_reopens_it(self):
        make_row(
            "busy@example.org",
            hard_count=0,
            soft_count=1,
            status=BouncedAddress.Status.DISMISSED,
            reviewed_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        # Gmail's 5.2.1 for a recipient receiving mail too fast, saved without a category (as the previous release
        # would): classified before it is counted.
        make_bounce(
            recipient="busy@example.org",
            category="",
            classification="hard",
            status_code="5.2.1",
            diagnostic_code=GMAIL_RECEIVING_RATE,
            match_method="message_id",
        )

        count_now()

        row = row_for("busy@example.org")
        self.assertEqual((row.category_counts, row.hard_count), ({"transient": 2}, 0))
        self.assertEqual((row.status, row.suggestion), (BouncedAddress.Status.DISMISSED, ""))
        self.assertFalse(row.actions.filter(action=BouncedAddressAction.Action.REOPEN).exists())

    def test_a_report_saved_without_a_category_is_classified_before_it_is_counted(self):
        bounce = make_bounce(recipient="u@example.org", category="", status_code="5.1.1")

        count_now()

        bounce.refresh_from_db()
        self.assertEqual(bounce.category, Category.HARD)
        self.assertEqual(row_for("u@example.org").category_counts, {"hard": 1})

    def test_an_unexpected_category_value_counts_as_unknown(self):
        make_bounce(recipient="x@example.org", category="mystery", classification="unknown")

        count_now()

        self.assertEqual(row_for("x@example.org").category_counts, {"unknown": 1})


def park_graph_cursor():
    """What ``mail.0026`` does when Graph reports were counted before categories existed."""
    BounceAggregationState.objects.filter(source="graph").update(
        cursor_at=aggregate.PARKED, cursor_id=aggregate.PARKED_ID
    )
