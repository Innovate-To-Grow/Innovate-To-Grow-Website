"""Page views are told apart by the browser's ``visitor_id``, never by the client IP.

Campus visitors share one public IP. The old throttle (60 a minute per IP) silently dropped most campus page views
on a busy day, and the admin statistics counted the whole campus as one unique visitor. The frontend now sends a
random ``visitor_id``: the throttle is keyed on it (120 a minute per visitor), requests without one share a single
``legacy`` bucket (600 a minute, for frontend bundles cached before the id existed), the id is stored, and the
statistics count ``COALESCE(visitor_id, ip_address)``.
"""

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from apps.cms.admin.analytics.page_view.stats import compute_dashboard_stats
from apps.cms.models import PageView
from apps.cms.services.analytics import VISITOR_ID_MAX_LENGTH, flush_sync
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
