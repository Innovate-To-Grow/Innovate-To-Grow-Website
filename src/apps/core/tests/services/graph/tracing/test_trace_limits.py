"""The Message Trace sync's ``EMAIL_MONITORING`` values are kept within safe bounds whatever the settings hold."""

from django.test import SimpleTestCase

from apps.core.services.email.graph.tracing import limits
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings


class TraceLimitsTests(SimpleTestCase):
    def test_the_defaults_are_used_as_they_are(self):
        self.assertEqual(limits.interval_seconds(), 1800)
        self.assertEqual(limits.max_requests_per_run(), 5)
        self.assertEqual(limits.page_size(), 1000)
        self.assertEqual(limits.min_age_minutes(), 15)
        self.assertEqual(limits.give_up_hours(), 48)
        self.assertEqual(limits.max_bytes(), 4 * 1024 * 1024)

    def test_values_below_the_floor_are_raised(self):
        low = {
            "trace_interval_seconds": 10,
            "trace_max_requests_per_run": 0,
            "trace_page_size": 0,
            "trace_min_age_minutes": 0,
            "trace_give_up_hours": 0,
            "trace_max_bytes": 1,
        }
        with monitoring_settings(**low):
            self.assertEqual(limits.interval_seconds(), 300)
            self.assertEqual(limits.max_requests_per_run(), 1)
            self.assertEqual(limits.page_size(), 1)
            self.assertEqual(limits.min_age_minutes(), 1)
            self.assertEqual(limits.give_up_hours(), 1)
            self.assertEqual(limits.max_bytes(), 64 * 1024)

    def test_values_above_the_ceiling_are_lowered(self):
        high = {
            "trace_max_requests_per_run": 1000,
            "trace_page_size": 100000,
            "trace_give_up_hours": 10**6,
            "trace_max_bytes": 10**12,
        }
        with monitoring_settings(**high):
            self.assertEqual(limits.max_requests_per_run(), 50)
            self.assertEqual(limits.page_size(), 5000)
            self.assertEqual(limits.give_up_hours(), limits.MAX_TRACE_AGE_HOURS)
            self.assertEqual(limits.max_bytes(), 32 * 1024 * 1024)

    def test_an_email_is_never_given_up_before_it_is_old_enough_to_trace(self):
        with monitoring_settings(trace_min_age_minutes=180, trace_give_up_hours=1):
            self.assertEqual(limits.give_up_hours(), 4)
