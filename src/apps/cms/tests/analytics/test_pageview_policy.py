"""The page-view limits are live request-limit policies: switched off, nothing is limited or counted; while the
request limiter is on, an admin edit applies without a restart."""

import uuid

from django.test import override_settings

from apps.cms.views.analytics import PageViewLegacyThrottle, PageViewTotalThrottle, PageViewVisitorThrottle
from apps.core.models import RequestRateLimitPolicy
from apps.core.services.request_limits.runtime import registry
from apps.core.tests.request_limits.helpers import isolate, view_limit

from .test_pageview_visitor import PageViewVisitorTestCase


class PageViewPolicyTests(PageViewVisitorTestCase):
    def setUp(self):
        super().setUp()
        isolate(self)

    def test_each_throttle_names_its_policy(self):
        self.assertEqual(
            [
                throttle.policy_scope
                for throttle in (PageViewVisitorThrottle, PageViewLegacyThrottle, PageViewTotalThrottle)
            ],
            ["view-pageview-visitor", "view-pageview-legacy", "view-pageview-total"],
        )

    @view_limit(**{"view-pageview-total": None, "view-pageview-visitor": None})
    def test_switched_off_policies_limit_and_count_nothing(self):
        visitor = str(uuid.uuid4())
        self.assertEqual({self.view(visitor) for _ in range(130)}, {201})
        total = PageViewTotalThrottle()
        self.assertTrue(total.record())

    @override_settings(REQUEST_RATE_LIMITS_ENABLED=True)
    def test_an_admin_edit_applies_without_a_restart(self):
        policy = RequestRateLimitPolicy.for_scope("view-pageview-visitor")
        policy.smart_enabled, policy.manual_requests = False, 2
        policy.save()
        registry.invalidate()
        visitor = str(uuid.uuid4())
        self.assertEqual([self.view(visitor) for _ in range(3)], [201, 201, 429])
