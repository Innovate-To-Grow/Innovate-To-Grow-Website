"""Rate signals: Retry-After parsing and clamping, which answers give back their usage, the pattern matchers and the
signal patterns in the settings."""

from datetime import timedelta
from email.utils import format_datetime

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from apps.core.services.delivery_rates import rules
from apps.core.services.delivery_rates.rules import signals
from apps.core.services.delivery_rates.rules.signals import SignalKind, parse_retry_after

from .helpers import START, rates_with


class RetryAfterTests(SimpleTestCase):
    def test_delta_seconds(self):
        self.assertEqual(parse_retry_after("10", now=START), 10.0)
        self.assertEqual(parse_retry_after(" 7 ", now=START), 7.0)
        self.assertEqual(parse_retry_after(30, now=START), 30.0)

    def test_a_future_http_date_is_the_time_until_it(self):
        when = format_datetime(START + timedelta(seconds=90), usegmt=True)

        self.assertEqual(parse_retry_after(when, now=START), 90.0)

    def test_a_past_http_date_or_zero_still_waits_one_second(self):
        past = format_datetime(START - timedelta(minutes=5), usegmt=True)

        self.assertEqual(parse_retry_after(past, now=START), 1.0)
        self.assertEqual(parse_retry_after("0", now=START), 1.0)

    def test_garbage_is_ignored(self):
        for value in ("", None, "soon", "-5", "1.5e3", "10 seconds", True, float("nan"), -3):
            with self.subTest(value=value):
                self.assertIsNone(parse_retry_after(value, now=START))

    def test_a_huge_value_is_capped_at_the_settings_maximum(self):
        maximum = settings.DELIVERY_RATES["controller"]["retry_after_max_seconds"]

        self.assertEqual(parse_retry_after("999999999999", now=START), maximum)
        self.assertEqual(
            parse_retry_after(format_datetime(START + timedelta(days=30), usegmt=True), now=START), maximum
        )

    @override_settings(DELIVERY_RATES=rates_with(controller={"retry_after_max_seconds": 120}))
    def test_the_cap_follows_the_settings(self):
        self.assertEqual(parse_retry_after("600", now=START), 120.0)


class SignalTests(SimpleTestCase):
    def test_constructors(self):
        self.assertEqual(signals.ok().kind, SignalKind.OK)
        self.assertEqual(signals.throttle(retry_after=3).retry_after, 3)
        self.assertEqual(signals.pause("connections", seconds=60).pause_seconds, 60)
        self.assertEqual(signals.quota("daily_quota", seconds=600).breaker_seconds, 600)
        self.assertEqual(signals.blocked("auth", scope=signals.Scope.BULK).scope, signals.Scope.BULK)
        self.assertTrue(signals.uncertain().uncertain)

    def test_usage_is_released_only_when_the_provider_certainly_did_not_take_the_request(self):
        released = {
            signals.ok(): False,
            signals.uncertain(): False,
            signals.throttle(): True,
            signals.throttle(uncertain=True): False,
            signals.pause("x", seconds=1): True,
            signals.quota("q"): True,
            signals.blocked("auth"): True,
            signals.none("opted_out"): True,
        }
        for signal, expected in released.items():
            with self.subTest(kind=signal.kind, uncertain=signal.uncertain):
                self.assertIs(signals.releases_usage(signal), expected)

    def test_matchers_ignore_case(self):
        self.assertTrue(signals.code_in("throttlingexception", ("ThrottlingException",)))
        self.assertFalse(signals.code_in("", ("",)))
        self.assertTrue(
            signals.text_has("454 Throttling failure: Daily message quota exceeded", ("daily MESSAGE quota",))
        )
        self.assertFalse(signals.text_has(None, ("x",)))

    def test_every_adapter_has_its_patterns(self):
        for adapter in ("graph", "ses", "smtp", "imap", "gmail_api", "sms"):
            with self.subTest(adapter=adapter):
                self.assertTrue(rules.defaults.signal_patterns(adapter))
