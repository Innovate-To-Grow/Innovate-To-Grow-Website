"""The CSP report limit is the live "view-csp-report" policy, seeded from CSP_REPORT_RATE_LIMIT /
CSP_REPORT_RATE_WINDOW_SECONDS."""

import importlib
import json
import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase

from apps.core.middleware.csp_report import csp_report
from apps.core.tests.request_limits.helpers import isolate, view_limit
from config.settings.base.integrations.request_limits import view_scopes

BODY = json.dumps({"csp-report": {"effective-directive": "img-src"}})


class CspReportPolicyTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)
        self.factory = RequestFactory()

    def post(self):
        return csp_report(self.factory.post("/csp-report/", data=BODY, content_type="application/json"))

    def logged(self, times):
        with patch("apps.core.middleware.csp_report.logger.warning") as warn:
            statuses = {self.post().status_code for _ in range(times)}
        self.assertEqual(statuses, {204})  # a dropped report is answered like a logged one
        return warn.call_count

    @view_limit(**{"view-csp-report": (2, 60)})
    def test_the_policy_rate_applies(self):
        self.assertEqual(self.logged(3), 2)

    @view_limit(**{"view-csp-report": None})
    def test_a_disabled_policy_limits_nothing(self):
        self.assertEqual(self.logged(70), 70)

    def test_the_seed_reads_the_deployment_env(self):
        with patch.dict(os.environ, {"CSP_REPORT_RATE_LIMIT": "7", "CSP_REPORT_RATE_WINDOW_SECONDS": "30"}):
            module = importlib.reload(view_scopes)
            spec = module.VIEW_SCOPES["view-csp-report"]
        importlib.reload(view_scopes)
        self.assertEqual((spec["requests"], spec["period_seconds"]), (7, 30))

    def test_a_bad_env_value_stops_the_start(self):
        from django.core.exceptions import ImproperlyConfigured

        with patch.dict(os.environ, {"CSP_REPORT_RATE_LIMIT": "many"}), self.assertRaises(ImproperlyConfigured):
            importlib.reload(view_scopes)
        importlib.reload(view_scopes)

    def test_a_non_positive_env_value_is_one(self):
        with patch.dict(os.environ, {"CSP_REPORT_RATE_LIMIT": "0"}):
            self.assertEqual(view_scopes._env_count("CSP_REPORT_RATE_LIMIT", 60), 1)
        self.assertEqual(view_scopes._env_count("UNSET_FOR_TEST_X", 60), 60)
