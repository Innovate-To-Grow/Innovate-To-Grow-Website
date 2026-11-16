from io import BytesIO

from django.apps import apps as django_apps
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from openpyxl import load_workbook

from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressCampaign
from apps.mail.services.email_monitoring.addresses import aggregate
from apps.mail.services.email_monitoring.addresses.actions import audit
from apps.mail.services.email_monitoring.addresses.listing.export import COLUMNS, export_rows
from apps.mail.tests.services.bounced_addresses.aggregate.test_categories import (
    Suggestion,
    park_graph_cursor,
    parking_migration,
    row_for,
)

from ..helpers import count_now, make_bounce, make_campaign, make_row, make_ses_log


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
