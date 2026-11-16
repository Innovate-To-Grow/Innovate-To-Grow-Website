import copy

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from apps.core.tests.project.config.settings.test_delivery_rates_settings import DEFAULTS, channel_override, load
from config.settings.base.integrations.delivery_rates.validation import load_delivery_rates, validate_delivery_rates


class DeliveryRatesValidationTests(SimpleTestCase):
    def assert_refused(self, overrides, message):
        with self.assertRaisesMessage(ImproperlyConfigured, message):
            load(overrides)

    def test_fractions_must_be_above_0_and_at_most_1(self):
        for bad in (0, -0.1, 1.5, True, "0.5", None):
            with self.subTest(value=bad):
                self.assert_refused(
                    channel_override("graph_send", headroom=bad), "graph_send.headroom must be a fraction"
                )
                self.assert_refused({"lanes": {"bulk_share": bad}}, "lanes.bulk_share must be a fraction")
                self.assert_refused({"controller": {"floor": bad}}, "controller.floor must be a fraction")
        self.assertEqual(load(channel_override("graph_send", headroom=1))["channels"]["graph_send"]["headroom"], 1)

    def test_counts_must_be_whole_numbers_of_at_least_1(self):
        for bad in (0, -1, 1.5, True, "3"):
            with self.subTest(value=bad):
                self.assert_refused(channel_override("ses_send", burst=bad), "ses_send.burst must be a whole number")
                self.assert_refused({"jobs": {"default_max_attempts": bad}}, "default_max_attempts must be a whole")
                self.assert_refused(
                    channel_override("gmail_api_send", daily_message_limit=bad),
                    "gmail_api_send.daily_message_limit must be a whole number",
                )

    def test_rates_and_seconds_must_be_positive_and_bounded(self):
        for bad in (0, -1, 10_000_000, "1", False):
            with self.subTest(value=bad):
                self.assert_refused(
                    channel_override("smtp_send", manual_rate=bad), "smtp_send.manual_rate must be a rate"
                )
        for bad in (0, -5, 10**9, None, "30"):
            with self.subTest(value=bad):
                self.assert_refused(
                    {"waits": {"dedicated_seconds": bad}}, "waits.dedicated_seconds must be a number of"
                )
        # JSON's 1e400 parses as infinity; "Infinity" itself is not JSON.
        with self.assertRaisesMessage(ImproperlyConfigured, "discovery.timeout_seconds must be a number of seconds"):
            load_delivery_rates(DEFAULTS, '{"discovery": {"timeout_seconds": 1e400}}')
        self.assert_refused({"discovery": {"timeout_seconds": float("inf")}}, "must be valid JSON")

    def test_the_manual_seed_cannot_exceed_the_provider_limit(self):
        self.assert_refused(channel_override("graph_send", manual_rate=31), "graph_send.manual_rate must not be above")
        self.assert_refused(
            channel_override("smtp_send", provider_limit=None, fallback_rate=None),
            "smtp_send needs a provider_limit or a fallback_rate",
        )

    def test_daily_limits_must_contain_their_parts(self):
        self.assert_refused(
            channel_override("graph_send", hourly_external_limit=10_001), "must not be above daily_limit"
        )
        self.assert_refused(channel_override("graph_send", unconfirmed_bulk_daily_limit=10_001), "must not be above")
        self.assert_refused(channel_override("gmail_api_send", daily_external_limit=3_001), "must not be above daily")
        self.assert_refused(channel_override("ses_send", backoff_initial_seconds=601), "must not be above the maximum")

    def test_shares_stored_on_the_policy_fit_its_columns(self):
        self.assert_refused(channel_override("gmail_api_send", transactional_reserve=1), "must be a share between 0")
        self.assert_refused({"lanes": {"transactional_reserve": None}}, "lanes.transactional_reserve must be set")
        self.assert_refused(channel_override("gmail_api_send", budget_headroom=0.0001), "must be a share between")
        merged = load(channel_override("gmail_api_send", transactional_reserve=0))
        self.assertEqual(merged["channels"]["gmail_api_send"]["transactional_reserve"], 0)

    def test_waits_stay_below_the_claim_recovery_and_the_request_budget(self):
        self.assert_refused({"waits": {"worker_seconds": 600}}, "below jobs.stale_claim_seconds")
        self.assert_refused({"jobs": {"stale_claim_seconds": 30}}, "below jobs.stale_claim_seconds")
        self.assert_refused({"waits": {"inline_seconds": 25}}, "inline_seconds must be below waits.inline_request")
        self.assert_refused({"waits": {"read_seconds": 30}}, "read_seconds must be below waits.inline_request")
        for channel in ("ses_send", "sms_send"):
            with self.subTest(channel=channel):
                self.assert_refused(
                    channel_override(channel, request_timeout_seconds=25),
                    f"channels.{channel}.request_timeout_seconds must be below waits.inline_request_budget_seconds",
                )
        self.assertEqual(
            load(channel_override("ses_send", request_timeout_seconds=20))["channels"]["ses_send"][
                "request_timeout_seconds"
            ],
            20,
        )

    def test_controller_and_runtime_rules(self):
        self.assert_refused({"controller": {"floor": 0.6}}, "controller.floor must not be above")
        self.assert_refused({"controller": {"start_factor": 0.4}}, "controller.floor must not be above")
        self.assert_refused({"controller": {"decrease_factor": 1}}, "decrease_factor must be below 1")
        self.assert_refused({"controller": {"breaker_probe_seconds": 30_000}}, "must not be above breaker_probe_max")
        self.assert_refused({"controller": {"backoff_jitter": 1}}, "backoff_jitter must be a share")
        self.assert_refused({"jobs": {"retry_base_seconds": 4_000}}, "retry_base_seconds must not be above")
        self.assert_refused({"usage": {"bucket_seconds": 7}}, "bucket_seconds must be a whole number of seconds")
        self.assert_refused({"usage": {"bucket_seconds": 300.5}}, "bucket_seconds must be a whole number of seconds")
        self.assert_refused({"usage": {"retention_seconds": 86_400}}, "retention_seconds must cover 24 hours")
        self.assert_refused({"usage": {"idle_state_seconds": 86_400}}, "idle_state_seconds must not be below")
        self.assert_refused({"jobs": {"gate_cache_seconds": 0}}, "gate_cache_seconds must be a number of seconds")

    def test_text_settings(self):
        for bad in ("UCMERCED.edu", "not a domain", "x@ucmerced.edu", 7):
            with self.subTest(value=bad):
                self.assert_refused(channel_override("gmail_api_send", internal_domain=bad), "internal_domain must be")
        merged = load(channel_override("gmail_api_send", internal_domain="ucmerced.edu"))
        self.assertEqual(merged["channels"]["gmail_api_send"]["internal_domain"], "ucmerced.edu")
        self.assert_refused(channel_override("graph_send", limits_confirmed="yes"), "must be true or false")

    def test_signal_patterns(self):
        for bad in ([], [""], ["ok", 7], "Throttling"):
            with self.subTest(value=bad):
                self.assert_refused({"signals": {"ses": {"throttle_codes": bad}}}, "signals.ses.throttle_codes must")
        for bad in ([99], [600], ["429"], [True]):
            with self.subTest(value=bad):
                self.assert_refused({"signals": {"graph": {"throttle_statuses": bad}}}, "three-digit status codes")

    def test_structure_errors_in_the_defaults_are_reported(self):
        config = copy.deepcopy(dict(settings.DELIVERY_RATES))
        del config["channels"]["graph_read"]["burst"]
        with self.assertRaisesMessage(ImproperlyConfigured, "channels.graph_read is missing burst"):
            validate_delivery_rates(config)
        config = copy.deepcopy(dict(settings.DELIVERY_RATES))
        config["channels"]["graph_read"]["typo_rate"] = 1
        with self.assertRaisesMessage(ImproperlyConfigured, "typo_rate is not a known delivery-rate setting"):
            validate_delivery_rates(config)
        config = copy.deepcopy(dict(settings.DELIVERY_RATES))
        del config["waits"]["read_seconds"]
        with self.assertRaisesMessage(ImproperlyConfigured, "waits is missing read_seconds"):
            validate_delivery_rates(config)
        config = copy.deepcopy(dict(settings.DELIVERY_RATES))
        del config["signals"]
        with self.assertRaisesMessage(ImproperlyConfigured, "must have exactly the sections"):
            validate_delivery_rates(config)
        with self.assertRaisesMessage(ImproperlyConfigured, "must have exactly the sections"):
            validate_delivery_rates([])
