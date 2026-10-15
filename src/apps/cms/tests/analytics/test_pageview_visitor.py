"""Page views are told apart by the browser's ``visitor_id``, never by the client IP.

Campus visitors share one public IP. The old throttle (60 a minute per IP) silently dropped most campus page views
on a busy day, and the admin statistics counted the whole campus as one unique visitor. The frontend now sends a
random ``visitor_id``: the throttle is keyed on it (120 a minute per visitor), requests without one share a single
``legacy`` bucket (600 a minute, for frontend bundles cached before the id existed), the id is stored, and the
statistics count ``COALESCE(visitor_id, ip_address)``.
"""

import importlib
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from apps.authn.models import ContactEmail
from apps.cms.admin.analytics.page_view.admin import PageViewAdmin
from apps.cms.admin.analytics.page_view.stats import compute_dashboard_stats
from apps.cms.models import PageView
from apps.cms.services.analytics import VISITOR_ID_MAX_LENGTH, clean_visitor_id, flush_sync
from apps.cms.views.analytics import (
    PageViewCreateView,
    PageViewLegacyThrottle,
    PageViewTotalThrottle,
    PageViewVisitorThrottle,
)

Member = get_user_model()

URL = "/analytics/pageview/"
CAMPUS_IP = "169.236.0.10"
VISITOR_RATE = 120
LEGACY_RATE = 600

MALFORMED_IDS = [
    "",
    " ",
    "a" * (VISITOR_ID_MAX_LENGTH + 1),
    "has space",
    "tab\tseparated",
    "trailing-newline\n",
    "semi;colon",
    "slash/path",
    "dots.are.not.safe",
    "<script>alert(1)</script>",
    "unicode-é",
    "１２３",
    12345,
    1.5,
    True,
    None,
    ["3f2b8c1e-5d4a-4f6b-9c7d-0a1b2c3d4e5f"],
    {"id": "3f2b8c1e-5d4a-4f6b-9c7d-0a1b2c3d4e5f"},
]


class ThrottleClock:
    """Stand-in for the throttles' ``timer``: every request of a test lands on one instant unless it is advanced."""

    def __init__(self):
        self.now = 1_790_000_000.0

    def __call__(self):
        return self.now


class PageViewVisitorTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.clock = ThrottleClock()
        for target, replacement in (
            # Keep every page view in the buffer until flush_sync(): no timer thread and no batch-size thread may
            # write behind the test's transaction.
            ("apps.cms.services.analytics.buffer._schedule_flush_locked", lambda: None),
            ("apps.cms.services.analytics.buffer._BATCH_SIZE", 10**9),
        ):
            patcher = patch(target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        for throttle in (PageViewVisitorThrottle, PageViewLegacyThrottle, PageViewTotalThrottle):
            patcher = patch.object(throttle, "timer", staticmethod(self.clock))
            patcher.start()
            self.addCleanup(patcher.stop)
        flush_sync()
        PageView.objects.all().delete()
        self.client = APIClient()

    # noinspection PyPep8Naming
    def tearDown(self):
        flush_sync()
        cache.clear()

    def view(self, visitor_id=None, path="/", **body):
        payload = {"path": path, **body}
        if visitor_id is not None:
            payload["visitor_id"] = visitor_id
        return self.client.post(
            URL, payload, format="json", REMOTE_ADDR=CAMPUS_IP, HTTP_X_FORWARDED_FOR=CAMPUS_IP
        ).status_code


class CampusPageViewTests(PageViewVisitorTestCase):
    def test_three_hundred_views_from_one_ip_by_a_hundred_visitors_are_all_stored(self):
        visitors = [str(uuid.uuid4()) for _ in range(100)]

        statuses = [self.view(visitor, path=f"/page-{turn}") for turn in range(3) for visitor in visitors]

        self.assertEqual(statuses, [201] * 300)
        flush_sync()
        self.assertEqual(PageView.objects.count(), 300)
        self.assertEqual(set(PageView.objects.values_list("ip_address", flat=True)), {CAMPUS_IP})
        self.assertEqual(set(PageView.objects.values_list("visitor_id", flat=True)), set(visitors))
        self.assertEqual(compute_dashboard_stats()["unique_visitors"], 100)

    def test_one_visitor_over_the_rate_is_throttled_without_affecting_anyone_else(self):
        noisy, quiet = str(uuid.uuid4()), str(uuid.uuid4())

        self.assertEqual([self.view(noisy) for _ in range(VISITOR_RATE)], [201] * VISITOR_RATE)
        self.assertEqual(self.view(noisy), 429)

        self.assertEqual(self.view(quiet), 201)
        self.assertEqual(self.view(), 201)  # an old bundle without an id, same IP
        self.assertEqual(self.view(noisy), 429)
        flush_sync()
        self.assertEqual(PageView.objects.filter(visitor_id=noisy).count(), VISITOR_RATE)
        self.assertEqual(PageView.objects.filter(visitor_id=quiet).count(), 1)

    def test_a_throttled_visitor_may_post_again_a_minute_later(self):
        visitor = str(uuid.uuid4())
        self.assertEqual([self.view(visitor) for _ in range(VISITOR_RATE)], [201] * VISITOR_RATE)
        self.assertEqual(self.view(visitor), 429)

        self.clock.now += 59
        self.assertEqual(self.view(visitor), 429)
        self.clock.now += 1

        self.assertEqual(self.view(visitor), 201)

    def test_the_client_ip_is_no_part_of_the_visitor_key(self):
        visitor = str(uuid.uuid4())
        for index in range(VISITOR_RATE):
            address = f"203.0.113.{index % 250 + 1}"
            response = self.client.post(
                URL,
                {"path": "/", "visitor_id": visitor},
                format="json",
                REMOTE_ADDR=address,
                HTTP_X_FORWARDED_FOR=f"{address}, 10.0.0.1",
            )
            self.assertEqual(response.status_code, 201)

        response = self.client.post(
            URL,
            {"path": "/", "visitor_id": visitor},
            format="json",
            REMOTE_ADDR="198.51.100.7",
            HTTP_X_FORWARDED_FOR="198.51.100.7",
        )
        self.assertEqual(response.status_code, 429)

    def test_throttle_keys_name_the_visitor_or_the_legacy_bucket_and_never_the_ip(self):
        visitor = str(uuid.uuid4())
        factory = APIRequestFactory()

        def keys(body):
            request = Request(
                factory.post(URL, body, format="json", REMOTE_ADDR=CAMPUS_IP, HTTP_X_FORWARDED_FOR=CAMPUS_IP),
                parsers=[JSONParser()],
            )
            return [throttle().get_cache_key(request, None) for throttle in PageViewCreateView.throttle_classes]

        self.assertEqual(PageViewCreateView.throttle_classes, [PageViewVisitorThrottle, PageViewLegacyThrottle])
        self.assertEqual(
            keys({"path": "/", "visitor_id": visitor}), [f"throttle_pageview_visitor_visitor:{visitor}", None]
        )
        self.assertEqual(keys({"path": "/"}), [None, "throttle_pageview_legacy_legacy"])
        self.assertEqual(keys({"path": "/", "visitor_id": "not valid!"}), [None, "throttle_pageview_legacy_legacy"])
        self.assertEqual(keys(["/"]), [None, "throttle_pageview_legacy_legacy"])


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


class VisitorStatsTests(TestCase):
    def setUp(self):
        cache.clear()
        flush_sync()
        PageView.objects.all().delete()

    @staticmethod
    def daily_visitors(stats):
        """The non-empty days of the seven-day visitor series, oldest first."""
        return [count for count in stats["last_7_days_visitors"] if count]

    def test_campus_visitors_behind_one_ip_are_counted_separately(self):
        for visitor in ("visitor-a", "visitor-a", "visitor-b", "visitor-c", "visitor-c"):
            PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id=visitor)

        stats = compute_dashboard_stats()

        self.assertEqual(stats["total_views"], 5)
        self.assertEqual(stats["unique_visitors"], 3)
        self.assertEqual(self.daily_visitors(stats), [3])

    def test_rows_without_a_visitor_id_keep_counting_by_ip(self):
        # Recorded before the frontend sent an id: two addresses, three rows.
        PageView.objects.create(path="/", ip_address="198.51.100.1")
        PageView.objects.create(path="/", ip_address="198.51.100.1")
        PageView.objects.create(path="/", ip_address="198.51.100.2")
        # New rows: two campus visitors behind one address, one of them twice.
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="visitor-a")
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="visitor-a")
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="visitor-b")
        # One visitor seen from two networks is still one visitor.
        PageView.objects.create(path="/", ip_address="203.0.113.9", visitor_id="visitor-b")

        stats = compute_dashboard_stats()

        self.assertEqual(stats["unique_visitors"], 4)
        self.assertEqual(self.daily_visitors(stats), [4])

    def test_a_row_with_neither_id_nor_ip_is_not_a_visitor(self):
        PageView.objects.create(path="/", ip_address=None)
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="visitor-a")

        stats = compute_dashboard_stats()

        self.assertEqual(stats["total_views"], 2)
        self.assertEqual(stats["unique_visitors"], 1)

    def test_daily_visitors_use_the_same_key(self):
        now = timezone.now()
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="today-a")
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="today-b")
        for visitor in ("old-a", "old-b", "old-c"):
            older = PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id=visitor)
            PageView.objects.filter(pk=older.pk).update(timestamp=now - timedelta(days=2))
        legacy = PageView.objects.create(path="/", ip_address="198.51.100.1")
        PageView.objects.filter(pk=legacy.pk).update(timestamp=now - timedelta(days=2))

        stats = compute_dashboard_stats()

        self.assertEqual(self.daily_visitors(stats), [4, 2])
        self.assertEqual(stats["unique_visitors"], 6)


class VisitorAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        flush_sync()
        PageView.objects.all().delete()
        self.admin_user = Member.objects.create_superuser(password="testpass123", first_name="A", last_name="Admin")
        ContactEmail.objects.create(
            member=self.admin_user, email_address="visitor-admin@example.com", email_type="primary", verified=True
        )
        self.client.login(username="visitor-admin@example.com", password="testpass123")

    def test_the_detail_page_shows_the_visitor_id_next_to_the_ip_address(self):
        page_view = PageView.objects.create(
            path="/about", ip_address=CAMPUS_IP, visitor_id="3f2b8c1e-5d4a-4f6b-9c7d-0a1b2c3d4e5f"
        )

        response = self.client.get(reverse("admin:cms_pageview_change", args=[page_view.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3f2b8c1e-5d4a-4f6b-9c7d-0a1b2c3d4e5f")
        self.assertContains(response, CAMPUS_IP)
        visitor_fields = dict(PageViewAdmin.fieldsets)["Visitor"]["fields"]
        self.assertEqual(visitor_fields.index("visitor_id"), visitor_fields.index("ip_address") + 1)
        self.assertIn("visitor_id", PageViewAdmin.readonly_fields)

    def test_page_views_can_be_searched_by_visitor_id(self):
        PageView.objects.create(path="/wanted", ip_address=CAMPUS_IP, visitor_id="visitor-wanted")
        PageView.objects.create(path="/other", ip_address=CAMPUS_IP, visitor_id="visitor-other")

        response = self.client.get(reverse("admin:cms_pageview_changelist"), {"q": "visitor-wanted"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row.path for row in response.context["cl"].result_list], ["/wanted"])
