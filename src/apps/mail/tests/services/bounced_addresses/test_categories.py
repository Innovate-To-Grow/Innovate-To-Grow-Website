"""Bounced addresses by bounce category: counting per category, the one recount after the upgrade, the rebuild that
classifies stored reports again, the category filter and sort, the audit text and the export, and mail.0026 (which
parks the Graph cursor so the previous release counts nothing while the deploy rolls out)."""

import importlib
from io import BytesIO

from django.apps import apps as django_apps
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from openpyxl import load_workbook

from apps.core.models import EmailBounce
from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressAction, BouncedAddressCampaign
from apps.mail.services.email_monitoring.addresses import aggregate, audit, listing, sources
from apps.mail.services.email_monitoring.addresses.export import COLUMNS, export_rows

from .helpers import count_now, make_bounce, make_campaign, make_row, make_ses_log

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


class RecountAfterUpgradeTests(TestCase):
    """``mail.0026`` parks the Graph cursor when Graph reports were counted before categories existed."""

    def setUp(self):
        cache.clear()

    def test_a_parked_cursor_counts_nothing_for_the_previous_release(self):
        make_bounce(recipient="p@example.org")
        count_now()
        park_graph_cursor()
        make_bounce(recipient="p@example.org", category="")
        state = BounceAggregationState.objects.get(source="graph")

        # The previous release reads the same cursor: no report is past it, and the page still loads.
        self.assertFalse(sources.after_cursor(EmailBounce.objects.all(), state, "created_at").exists())
        self.assertEqual(aggregate.pending(), 0)

    def test_the_first_count_starts_the_graph_counts_again_once_and_keeps_the_ses_counts(self):
        make_bounce(
            recipient="old@example.org",
            category="",
            classification="hard",
            status_code="5.4.316",
            match_method="message_id",
        )
        make_ses_log(make_campaign(), "old@example.org", bounce_type="Permanent")
        count_now()
        # As the release before categories left it: the report counted as hard, without category counts.
        BouncedAddress.objects.filter(address="old@example.org").update(
            hard_count=1, soft_count=0, category_counts={}, last_category="", suggestion=Suggestion.UNDELIVERABLE
        )
        EmailBounce.objects.update(category="", classification="hard")
        park_graph_cursor()

        count_now()

        row = row_for("old@example.org")
        self.assertEqual((row.hard_count, row.soft_count, row.matched_count), (0, 1, 1))
        self.assertEqual((row.category_counts, row.last_category), ({"transient": 1}, "transient"))
        self.assertEqual(row.ses_permanent_count, 1)
        self.assertEqual(row.suggestion, Suggestion.UNDELIVERABLE)  # the SES permanent bounce, not the timeout
        state = BounceAggregationState.objects.get(source="graph")
        self.assertLess(state.cursor_at, aggregate.PARKED)
        self.assertEqual(state.processed_total, 1)
        entry = BouncedAddressAction.objects.get(action=BouncedAddressAction.Action.REBUILD)
        self.assertEqual((entry.actor, entry.details), (None, {"source": "graph"}))
        self.assertTrue(entry.actor_label.startswith("Automatic"))
        self.assertEqual(BouncedAddressCampaign.objects.filter(source="ses").count(), 1)

        count_now()

        self.assertEqual(row_for("old@example.org").soft_count, 1)
        self.assertEqual(BouncedAddressAction.objects.filter(action="rebuild").count(), 1)

    def test_an_address_with_only_ses_events_is_left_as_it_is(self):
        make_ses_log(make_campaign(), "ses@example.org", bounce_type="Transient")
        count_now()
        before = row_for("ses@example.org")
        BounceAggregationState.objects.update_or_create(
            source="graph", defaults={"cursor_at": aggregate.PARKED, "processed_total": 1}
        )

        count_now()

        after = row_for("ses@example.org")
        self.assertEqual(
            (after.ses_transient_count, after.first_bounce_at, after.suggestion),
            (before.ses_transient_count, before.first_bounce_at, before.suggestion),
        )


class SelfHealTests(TestCase):
    """Every report this release counts adds one to a classification count and one to a category count."""

    def setUp(self):
        cache.clear()

    def test_a_row_whose_counts_do_not_add_up_has_the_graph_counts_started_again(self):
        make_bounce(recipient="h@example.org", category="transient", classification="soft", status_code="5.4.316")
        count_now()
        # As if the release before categories counted a report during the rollout: a classification count only.
        BouncedAddress.objects.filter(address="h@example.org").update(hard_count=1)
        self.assertFalse(aggregate.graph_counts_agree(row_for("h@example.org")))

        aggregate.refresh_all()
        self.assertEqual(BounceAggregationState.objects.get(source="graph").cursor_at, aggregate.PARKED)
        count_now()

        row = row_for("h@example.org")
        self.assertEqual((row.hard_count, row.soft_count, row.category_counts), (0, 1, {"transient": 1}))
        self.assertTrue(aggregate.graph_counts_agree(row))
        self.assertEqual(BouncedAddressAction.objects.filter(action="rebuild").count(), 1)

    def test_rows_that_add_up_leave_the_cursor_alone(self):
        make_bounce(recipient="ok@example.org")
        make_ses_log(make_campaign(), "ses-only@example.org", bounce_type="Transient")
        count_now()
        cursor = BounceAggregationState.objects.get(source="graph").cursor_at

        aggregate.refresh_all()

        self.assertEqual(BounceAggregationState.objects.get(source="graph").cursor_at, cursor)

    def test_parking_creates_the_counting_state_when_there_is_none(self):
        aggregate.park_graph()

        self.assertEqual(BounceAggregationState.objects.get(source="graph").cursor_at, aggregate.PARKED)


class RebuildTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_rebuild_classifies_the_stored_reports_again_then_counts_them(self):
        bounce = make_bounce(recipient="r@example.org", status_code="5.0.0", diagnostic_code=TIMEOUT)
        count_now()
        self.assertEqual(row_for("r@example.org").category_counts, {"hard": 1})
        park_graph_cursor()

        reclassified = aggregate.rebuild()
        self.assertIsNone(BounceAggregationState.objects.get(source="graph").cursor_at)
        count_now()

        bounce.refresh_from_db()
        row = row_for("r@example.org")
        self.assertEqual(reclassified, 1)
        self.assertEqual(bounce.category, Category.TRANSIENT)
        self.assertEqual((row.category_counts, row.hard_count, row.soft_count), ({"transient": 1}, 0, 1))
        self.assertFalse(BouncedAddressAction.objects.filter(action="rebuild").exists())  # the view records it


class ListingTests(TestCase):
    def setUp(self):
        cache.clear()
        make_row("hard@example.org")
        make_row("timeout@example.org", hard_count=0, soft_count=2, last_category="transient")
        make_row(
            "relay@example.org",
            hard_count=0,
            rejected_count=1,
            category_counts={"relay_denied": 1},
            last_category="relay_denied",
        )
        make_row("ses@example.org", hard_count=0, ses_transient_count=1, last_category="")

    def addresses(self, **params):
        current = listing.parse_listing({"status": "all", **params})
        return [row.address for row in listing.rows_for(current)]

    def test_the_category_filter_reads_graph_categories_and_the_ses_type_that_means_the_same(self):
        self.assertEqual(self.addresses(category="relay_denied"), ["relay@example.org"])
        self.assertEqual(sorted(self.addresses(category="transient")), ["ses@example.org", "timeout@example.org"])
        self.assertEqual(self.addresses(category="hard"), ["hard@example.org"])
        self.assertEqual(self.addresses(category="mailbox_disabled"), [])
        self.assertEqual(len(self.addresses(category="bogus")), 4)
        labels = {key: label for key, (label, _q) in listing.CATEGORIES.items()}
        self.assertEqual(labels["transient"], "Temporary failure (or SES transient)")
        self.assertEqual(labels["relay_denied"], "Relay denied")

    def test_rows_sort_by_their_last_category(self):
        self.assertEqual(
            self.addresses(sort="category", dir="asc"),
            ["ses@example.org", "hard@example.org", "relay@example.org", "timeout@example.org"],
        )


class EvidenceAndExportTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_the_audit_evidence_names_the_category(self):
        row = make_row("e@example.org")
        old = make_row("legacy@example.org", last_category="")

        self.assertEqual(audit.evidence(row), "address does not exist 5.1.1, 1 report")
        self.assertEqual(audit.evidence(old), "hard bounce 5.1.1, 1 report")

    def test_the_export_lists_the_categories_and_the_last_category(self):
        make_row("x@example.org", category_counts={"transient": 2, "spam_rejected": 1}, last_category="spam_rejected")

        sheet = load_workbook(BytesIO(export_rows(BouncedAddress.objects.all()))).active
        header = [cell.value for cell in sheet[1]]
        values = dict(zip(header, [cell.value for cell in sheet[2]], strict=True))

        self.assertEqual(header, [label for label, _width in COLUMNS])
        self.assertEqual(values["Categories"], "Temporary failure 2; Spam or reputation rejection 1")
        self.assertEqual(values["Last category"], "Spam or reputation rejection")


class ParkingMigrationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_the_cursor_is_parked_only_when_graph_reports_were_counted(self):
        parking_migration.park_graph_counting(django_apps, None)
        self.assertFalse(BounceAggregationState.objects.exists())

        BounceAggregationState.objects.create(source="graph", processed_total=0)
        BounceAggregationState.objects.create(source="ses", processed_total=5, cursor_at=timezone.now())
        parking_migration.park_graph_counting(django_apps, None)
        self.assertIsNone(BounceAggregationState.objects.get(source="graph").cursor_at)

        BounceAggregationState.objects.filter(source="graph").update(processed_total=3, cursor_at=timezone.now())
        parking_migration.park_graph_counting(django_apps, None)
        states = {state.source: state for state in BounceAggregationState.objects.all()}
        self.assertEqual(
            (states["graph"].cursor_at, states["graph"].cursor_id), (aggregate.PARKED, aggregate.PARKED_ID)
        )
        self.assertLess(states["ses"].cursor_at, aggregate.PARKED)
        self.assertEqual(
            (parking_migration.PARKED, parking_migration.PARKED_ID), (aggregate.PARKED, aggregate.PARKED_ID)
        )

    def test_the_reverse_unparks_with_zeroed_graph_counts_and_removes_the_new_suggestions(self):
        make_bounce(recipient="g@example.org")
        make_ses_log(make_campaign(), "s@example.org", bounce_type="Transient")
        count_now()
        park_graph_cursor()
        relay = make_row("relay@example.org", hard_count=0, rejected_count=1, suggestion=Suggestion.RELAY)

        parking_migration.unpark_graph_counting(django_apps, None)

        state = BounceAggregationState.objects.get(source="graph")
        self.assertEqual((state.cursor_at, state.processed_total), (None, 0))
        graph = row_for("g@example.org")
        self.assertEqual((graph.hard_count, graph.graph_last_at, graph.last_classification), (0, None, ""))
        self.assertFalse(BouncedAddressCampaign.objects.filter(source="graph").exists())
        self.assertEqual(row_for("s@example.org").ses_transient_count, 1)
        relay.refresh_from_db()
        self.assertEqual(relay.suggestion, "")

    def test_the_reverse_leaves_an_unparked_cursor_and_its_counts_alone(self):
        make_bounce(recipient="g@example.org")
        count_now()

        parking_migration.unpark_graph_counting(django_apps, None)

        self.assertEqual(row_for("g@example.org").hard_count, 1)
        self.assertIsNotNone(BounceAggregationState.objects.get(source="graph").cursor_at)


class MailMigrationRoundTripTests(TransactionTestCase):
    """Migrate mail back to 0025 and forward again."""

    BEFORE = ("mail", "0025_sms_link_revocation")
    AFTER = ("mail", "0026_bounced_address_categories")

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_forward_parks_the_cursor_old_saves_get_the_defaults_and_reverse_unparks(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.BEFORE])
        old_apps = executor.loader.project_state([self.BEFORE]).apps
        old_state = old_apps.get_model("mail", "BounceAggregationState")
        old_state.objects.create(source="graph", processed_total=4, cursor_at=timezone.now())

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.AFTER])

        new_apps = executor.loader.project_state([self.AFTER]).apps
        self.assertEqual(old_state.objects.get(source="graph").cursor_at, aggregate.PARKED)
        # The previous release, still counting while the deploy rolls out, saves without the new columns.
        old_apps.get_model("mail", "BouncedAddress").objects.create(address="during@example.org")
        saved = new_apps.get_model("mail", "BouncedAddress").objects.get(address="during@example.org")
        self.assertEqual((saved.category_counts, saved.last_category), ({}, ""))

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.BEFORE])
        self.assertEqual(old_state.objects.get(source="graph").cursor_at, None)
