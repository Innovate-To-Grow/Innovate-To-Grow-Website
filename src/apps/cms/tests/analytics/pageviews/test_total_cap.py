import logging
import uuid
from unittest.mock import patch

from django.test import override_settings

from apps.cms.models import PageView
from apps.cms.services.analytics import (
    flush_sync,
)
from apps.cms.tests.analytics.pageviews.test_pageview_limits import (
    THROTTLED_DETAIL,
    TOTAL_KEY,
    TOTAL_RATE,
    VIEW_LOGGER,
    WARNED_KEY,
    stored_keys,
    total_count,
)
from apps.cms.views.analytics import (
    PageViewCreateView,
    PageViewLegacyThrottle,
    PageViewTotalThrottle,
    PageViewVisitorThrottle,
)
from apps.core.tests.request_limits.helpers import view_limit
from apps.core.utils.throttle_cache import throttle_cache

from .test_pageview_visitor import CAMPUS_IP, LEGACY_RATE, URL, VISITOR_RATE, PageViewVisitorTestCase


@override_settings(REQUEST_RATE_LIMITS_ENABLED=False)  # one client floods the site cap (see above)
class TotalCapTests(PageViewVisitorTestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        super().setUp()
        # Reaching the cap logs an operator warning; keep it out of the test output (assertLogs still sees it).
        view_logger = logging.getLogger(VIEW_LOGGER)
        handler = logging.NullHandler()
        view_logger.addHandler(handler)
        self.addCleanup(view_logger.removeHandler, handler)
        propagate = patch.object(view_logger, "propagate", False)
        propagate.start()
        self.addCleanup(propagate.stop)

    def response(self, visitor_id=None):
        payload = {"path": "/"} if visitor_id is None else {"path": "/", "visitor_id": visitor_id}
        return self.client.post(URL, payload, format="json", REMOTE_ADDR=CAMPUS_IP, HTTP_X_FORWARDED_FOR=CAMPUS_IP)

    def test_the_cap_is_three_thousand_a_minute_under_one_constant_key(self):
        throttle = PageViewTotalThrottle()

        self.assertEqual(PageViewTotalThrottle.policy_scope, "view-pageview-total")
        self.assertEqual((throttle.num_requests, throttle.duration), (TOTAL_RATE, 60))
        self.assertEqual(throttle.get_cache_key(None, None), TOTAL_KEY)
        # Checked around the per-visitor / legacy throttles, not as one of them (see check_throttles).
        self.assertEqual(PageViewCreateView.throttle_classes, [PageViewVisitorThrottle, PageViewLegacyThrottle])

    def test_three_thousand_visitors_in_a_minute_are_stored_and_the_next_page_view_is_refused(self):
        visitors = [str(uuid.uuid4()) for _ in range(TOTAL_RATE)]

        statuses = [self.view(visitor) for visitor in visitors]

        self.assertEqual(statuses.count(201), TOTAL_RATE)
        self.assertEqual(len(statuses), TOTAL_RATE)
        # The 3001st page view of the minute, whoever sends it: a new visitor, an old bundle, a known visitor.
        self.assertEqual(self.view(str(uuid.uuid4())), 429)
        self.assertEqual(self.view(), 429)
        self.assertEqual(self.view(visitors[0]), 429)
        flush_sync()
        self.assertEqual(PageView.objects.count(), TOTAL_RATE)
        self.assertEqual(set(PageView.objects.values_list("visitor_id", flat=True)), set(visitors))
        self.assertEqual(stored_keys("default"), set())

    def test_the_cap_frees_up_a_minute_later(self):
        for _ in range(TOTAL_RATE):
            self.view(str(uuid.uuid4()))
        self.assertEqual(self.view(str(uuid.uuid4())), 429)

        self.clock.now += 59
        self.assertEqual(self.view(str(uuid.uuid4())), 429)
        self.clock.now += 1

        self.assertEqual(self.view(str(uuid.uuid4())), 201)
        self.assertEqual(total_count(), 1)

    def test_the_refusal_is_the_same_429_the_per_visitor_rate_answers(self):
        noisy = str(uuid.uuid4())
        for _ in range(VISITOR_RATE):
            self.response(noisy)
        per_visitor = self.response(noisy)
        self.assertEqual(total_count(), VISITOR_RATE)

        with view_limit(**{"view-pageview-total": (VISITOR_RATE, 60)}):
            over_the_cap = self.response(str(uuid.uuid4()))

        for response in (per_visitor, over_the_cap):
            self.assertEqual(response.status_code, 429)
            self.assertEqual(str(response.data["detail"]), THROTTLED_DETAIL)
            self.assertEqual(response.data["detail"].code, "throttled")
            self.assertEqual(response["Retry-After"], "60")
        self.assertEqual(over_the_cap.data, per_visitor.data)

    def test_page_views_refused_by_the_per_visitor_rate_do_not_use_up_the_total(self):
        """One runaway browser costs 120 of the 3,000, however fast it loops."""
        runaway = str(uuid.uuid4())

        statuses = [self.view(runaway) for _ in range(500)]

        self.assertEqual(statuses, [201] * VISITOR_RATE + [429] * (500 - VISITOR_RATE))
        self.assertEqual(total_count(), VISITOR_RATE)

    def test_page_views_refused_by_the_legacy_rate_do_not_use_up_the_total(self):
        statuses = [self.view() for _ in range(LEGACY_RATE + 50)]

        self.assertEqual(statuses, [201] * LEGACY_RATE + [429] * 50)
        self.assertEqual(total_count(), LEGACY_RATE)

    def test_over_the_cap_nothing_is_counted_and_a_minted_id_gets_no_bucket(self):
        with view_limit(**{"view-pageview-total": (5, 60)}):
            self.assertEqual([self.view(str(uuid.uuid4())) for _ in range(5)], [201] * 5)
            keys_at_the_cap = stored_keys("throttle")
            minted = [str(uuid.uuid4()) for _ in range(20)]

            self.assertEqual([self.view(visitor) for visitor in minted], [429] * 20)
            self.assertEqual(self.view(), 429)

            # Nothing new but the once-a-minute marker of the operator warning.
            self.assertEqual(stored_keys("throttle"), keys_at_the_cap | {WARNED_KEY})
            self.assertEqual(total_count(), 5)
        flush_sync()
        self.assertEqual(PageView.objects.count(), 5)

    def test_reaching_the_cap_is_logged_once_a_minute_for_operators(self):
        with view_limit(**{"view-pageview-total": (3, 60)}):
            with self.assertLogs(VIEW_LOGGER, level="WARNING") as logs:
                statuses = [self.view(str(uuid.uuid4())) for _ in range(30)]

            self.assertEqual(statuses, [201] * 3 + [429] * 27)
            self.assertEqual(len(logs.records), 1)
            message = logs.records[0].getMessage()
            self.assertTrue(message.startswith("analytics.pageview_total_cap limit=3 window_seconds=60"), message)
            # No visitor id, path or address in the line.
            self.assertNotIn(CAMPUS_IP, message)

            # A minute later the marker has expired: the next refusal is reported again.
            throttle_cache.delete(WARNED_KEY)
            with self.assertLogs(VIEW_LOGGER, level="WARNING") as logs:
                self.assertEqual(self.view(str(uuid.uuid4())), 429)
            self.assertEqual(len(logs.records), 1)

    def test_nothing_is_logged_below_the_cap(self):
        noisy = str(uuid.uuid4())

        with self.assertNoLogs(VIEW_LOGGER, level="WARNING"):
            statuses = [self.view(noisy) for _ in range(VISITOR_RATE + 5)]
            self.view()

        self.assertEqual(statuses.count(429), 5)
        self.assertNotIn(WARNED_KEY, stored_keys("throttle"))

    def test_honest_visitors_below_the_cap_keep_their_own_rate(self):
        visitors = [str(uuid.uuid4()) for _ in range(20)]

        for visitor in visitors:
            self.assertEqual([self.view(visitor) for _ in range(VISITOR_RATE)], [201] * VISITOR_RATE)

        # 2,400 page views so far: under the cap, so each visitor meets only their own 120 a minute.
        self.assertEqual([self.view(visitor) for visitor in visitors], [429] * 20)
        self.assertEqual(self.view(str(uuid.uuid4())), 201)
        self.assertEqual(self.view(), 201)
        self.assertEqual(total_count(), 20 * VISITOR_RATE + 2)
        flush_sync()
        self.assertEqual(PageView.objects.count(), 20 * VISITOR_RATE + 2)

    def test_the_client_ip_is_no_part_of_the_cap(self):
        with view_limit(**{"view-pageview-total": (3, 60)}):
            for index in range(3):
                address = f"203.0.113.{index + 1}"
                response = self.client.post(
                    URL,
                    {"path": "/", "visitor_id": str(uuid.uuid4())},
                    format="json",
                    REMOTE_ADDR=address,
                    HTTP_X_FORWARDED_FOR=address,
                )
                self.assertEqual(response.status_code, 201)

            response = self.client.post(
                URL,
                {"path": "/", "visitor_id": str(uuid.uuid4())},
                format="json",
                REMOTE_ADDR="198.51.100.7",
                HTTP_X_FORWARDED_FOR="198.51.100.7",
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(stored_keys("throttle") & {TOTAL_KEY}, {TOTAL_KEY})
        self.assertFalse([key for key in stored_keys("throttle") if "203.0.113" in key or "198.51.100" in key])
