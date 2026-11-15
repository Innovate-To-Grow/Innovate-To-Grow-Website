import importlib
import uuid

from django.db import connection
from django.test import SimpleTestCase, override_settings

from apps.cms.models import PageView
from apps.cms.services.analytics import VISITOR_ID_MAX_LENGTH, clean_visitor_id, flush_sync
from apps.cms.tests.analytics.pageviews.test_pageview_visitor import (
    CAMPUS_IP,
    LEGACY_RATE,
    MALFORMED_IDS,
    URL,
    PageViewVisitorTestCase,
)


# Six hundred views from one test client: with the request limiter on, the telemetry scope's per-IP ceiling would
# refuse them before the shared legacy bucket under test fills.
@override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
class LegacyBucketTests(PageViewVisitorTestCase):
    def test_views_without_an_id_share_one_bucket_of_six_hundred_a_minute(self):
        self.assertEqual([self.view() for _ in range(LEGACY_RATE)], [201] * LEGACY_RATE)

        self.assertEqual(self.view(), 429)
        # Visitors that send an id are not in that bucket.
        self.assertEqual(self.view(str(uuid.uuid4())), 201)
        flush_sync()
        self.assertEqual(PageView.objects.filter(visitor_id__isnull=True).count(), LEGACY_RATE)

    def test_a_view_without_an_id_is_stored_with_a_null_visitor(self):
        self.assertEqual(self.view(path="/about", referrer="https://example.com/"), 201)

        flush_sync()
        page_view = PageView.objects.get()
        self.assertIsNone(page_view.visitor_id)
        self.assertEqual(page_view.ip_address, CAMPUS_IP)
        self.assertEqual(page_view.path, "/about")

    def test_malformed_ids_are_ignored_and_fall_into_the_legacy_bucket(self):
        for bad in MALFORMED_IDS:
            with self.subTest(visitor_id=bad):
                response = self.client.post(URL, {"path": "/", "visitor_id": bad}, format="json")
                self.assertEqual(response.status_code, 201)

        flush_sync()
        self.assertEqual(PageView.objects.count(), len(MALFORMED_IDS))
        self.assertEqual(set(PageView.objects.values_list("visitor_id", flat=True)), {None})
        # One shared bucket, not one bucket per junk value: the junk above already used part of it.
        remaining = LEGACY_RATE - len(MALFORMED_IDS)
        self.assertEqual([self.view() for _ in range(remaining)], [201] * remaining)
        self.assertEqual(self.view("not valid!"), 429)
        self.assertEqual(self.view(), 429)

    def test_a_body_that_is_not_an_object_is_a_plain_400(self):
        response = self.client.post(URL, ["/about"], format="json")

        self.assertEqual(response.status_code, 400)
        flush_sync()
        self.assertEqual(PageView.objects.count(), 0)


class VisitorIdStorageTests(PageViewVisitorTestCase):
    def test_well_formed_ids_are_stored_as_sent(self):
        ids = [
            "3f2b8c1e-5d4a-4f6b-9c7d-0a1b2c3d4e5f",
            "3F2B8C1E-5D4A-4F6B-9C7D-0A1B2C3D4E5F",
            "A" * VISITOR_ID_MAX_LENGTH,
            "short_id-1",
            "x",
        ]
        for visitor_id in ids:
            self.assertEqual(self.view(visitor_id), 201)

        flush_sync()
        self.assertEqual(sorted(PageView.objects.values_list("visitor_id", flat=True)), sorted(ids))

    def test_the_ip_address_is_still_recorded_next_to_the_visitor_id(self):
        visitor = str(uuid.uuid4())
        self.assertEqual(self.view(visitor), 201)

        flush_sync()
        page_view = PageView.objects.get()
        self.assertEqual((page_view.visitor_id, page_view.ip_address), (visitor, CAMPUS_IP))

    def test_the_column_is_nullable_and_as_long_as_the_longest_accepted_id(self):
        field = PageView._meta.get_field("visitor_id")

        self.assertTrue(field.null)
        self.assertEqual(field.max_length, VISITOR_ID_MAX_LENGTH)

    def test_the_column_has_no_index(self):
        """Nothing filters on it (the statistics count an expression), and it is the largest write-heavy table."""
        field = PageView._meta.get_field("visitor_id")
        self.assertFalse(field.db_index)
        self.assertFalse(field.unique)
        self.assertEqual([index.fields for index in PageView._meta.indexes], [["path", "timestamp"]])

        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, PageView._meta.db_table)
        self.assertEqual(
            [name for name, details in constraints.items() if "visitor_id" in (details["columns"] or [])], []
        )
        # The other single-column indexes are still there (so the introspection above really lists indexes).
        indexed = {tuple(details["columns"]) for details in constraints.values() if details["index"]}
        self.assertTrue({("path",), ("ip_address",), ("session_key",), ("timestamp",)} <= indexed)

    def test_the_migration_only_adds_the_nullable_column(self):
        migration = importlib.import_module("apps.cms.migrations.0020_pageview_visitor_id").Migration

        self.assertEqual([type(operation).__name__ for operation in migration.operations], ["AddField"])
        (add_field,) = migration.operations
        self.assertEqual((add_field.model_name, add_field.name), ("pageview", "visitor_id"))
        self.assertTrue(add_field.field.null)
        self.assertFalse(add_field.field.db_index)
        self.assertEqual(add_field.field.max_length, VISITOR_ID_MAX_LENGTH)


class CleanVisitorIdTests(SimpleTestCase):
    def test_accepts_uuids_and_short_url_safe_tokens(self):
        for value in (str(uuid.uuid4()), uuid.uuid4().hex, "a", "A_b-9", "z" * VISITOR_ID_MAX_LENGTH):
            with self.subTest(value=value):
                self.assertEqual(clean_visitor_id(value), value)

    def test_rejects_everything_else(self):
        for value in MALFORMED_IDS:
            with self.subTest(value=value):
                self.assertIsNone(clean_visitor_id(value))
