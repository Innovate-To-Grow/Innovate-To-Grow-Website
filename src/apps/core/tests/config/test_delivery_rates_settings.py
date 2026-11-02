"""DELIVERY_RATES: the per-channel seeds, the env overrides deep-merged into them, and the validation at import."""

import copy
import importlib
import json
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from apps.core.models import DeliveryRatePolicy
from apps.core.models.base import delivery_rates as policy_module
from config.settings.base.integrations import delivery_rates as rates_settings
from config.settings.base.integrations.delivery_rates import validation
from config.settings.base.integrations.delivery_rates.validation import load_delivery_rates, validate_delivery_rates

DEFAULTS = rates_settings.DEFAULTS


def load(overrides):
    return load_delivery_rates(DEFAULTS, json.dumps(overrides))


def channel_override(channel, **values):
    return {"channels": {channel: values}}


class DeliveryRatesDefaultsTests(SimpleTestCase):
    def test_the_settings_carry_the_validated_defaults(self):
        self.assertEqual(settings.DELIVERY_RATES, load_delivery_rates(DEFAULTS))
        self.assertEqual(rates_settings.__all__, ["DELIVERY_RATES"])

    def test_every_policy_channel_has_seeds_and_smart_rate_is_on_everywhere(self):
        channels = settings.DELIVERY_RATES["channels"]
        self.assertEqual(set(channels), set(DeliveryRatePolicy.Channel.values))
        self.assertEqual(set(channels), set(policy_module.CHANNEL_UNITS))
        for name, spec in channels.items():
            with self.subTest(channel=name):
                self.assertIs(spec["smart_enabled"], True)
                self.assertTrue(spec["provider_limit"] is not None or spec["fallback_rate"] is not None)

    def test_documented_limits_and_their_sources(self):
        channels = settings.DELIVERY_RATES["channels"]
        graph, gmail, sms = channels["graph_send"], channels["gmail_api_send"], channels["sms_send"]
        self.assertEqual((graph["manual_rate"], graph["provider_limit"], graph["daily_limit"]), (24, 30, 10_000))
        self.assertEqual((graph["hourly_external_limit"], graph["hourly_internal_limit"]), (500, 1_000))
        self.assertEqual(graph["unconfirmed_bulk_daily_limit"], 1_000)
        self.assertEqual(channels["graph_read"]["provider_limit"], 1_000)
        self.assertEqual((gmail["manual_rate"], gmail["provider_limit"]), (20, 60))
        self.assertEqual(
            (gmail["daily_message_limit"], gmail["daily_limit"], gmail["daily_external_limit"]), (2_000, 3_000, 2_000)
        )
        self.assertEqual(
            (gmail["budget_headroom"], gmail["transactional_reserve"], gmail["internal_domain"]), (0.9, 0.25, "")
        )
        self.assertEqual((sms["provider_limit"], sms["parts_limit"], sms["parts_fallback_rate"]), (1, None, 1))
        self.assertEqual((channels["ses_send"]["provider_limit"], channels["ses_send"]["fallback_rate"]), (None, 1))
        profiles = channels["smtp_send"]["host_profiles"]
        self.assertEqual(profiles["smtp.gmail.com"], {"daily_message_limit": 2_000})
        self.assertEqual(profiles["smtp-relay.gmail.com"], {"daily_message_limit": 10_000, "daily_limit": 10_000})
        text = Path(rates_settings.channels.__file__).read_text(encoding="utf-8")
        for url in (
            "learn.microsoft.com",
            "docs.aws.amazon.com",
            "developers.google.com",
            "knowledge.workspace.google.com",
        ):
            self.assertIn(f"https://{url}/", text)

    def test_runtime_defaults_keep_their_rules(self):
        rates = settings.DELIVERY_RATES
        self.assertLess(rates["waits"]["worker_seconds"], rates["jobs"]["stale_claim_seconds"])
        self.assertLess(rates["waits"]["inline_seconds"], rates["waits"]["inline_request_budget_seconds"])
        self.assertEqual(rates["lanes"], {"bulk_share": 0.8, "transactional_reserve": 0.10})
        self.assertEqual(
            rates["usage"], {"bucket_seconds": 300, "retention_seconds": 172_800, "idle_state_seconds": 2_592_000}
        )
        self.assertEqual(rates["jobs"]["stale_claim_seconds"], 600)
        self.assertEqual((rates["jobs"]["defer_jitter_seconds"], rates["jobs"]["gate_cache_seconds"]), (1, 1))

    def test_the_bounds_match_the_policy_columns(self):
        manual = DeliveryRatePolicy._meta.get_field("manual_rate")
        largest = 10 ** (manual.max_digits - manual.decimal_places) - 10**-manual.decimal_places
        self.assertAlmostEqual(validation.MAX_RATE, largest)
        self.assertEqual(validation.MIN_RATE, float(policy_module.MIN_RATE))
        self.assertEqual(validation.MAX_RESERVE, float(policy_module.MAX_RESERVE))
        self.assertEqual(validation.MIN_SHARE, float(policy_module.MIN_RATE))

    def test_pattern_lists_are_tuples(self):
        for adapter, patterns in settings.DELIVERY_RATES["signals"].items():
            for name, value in patterns.items():
                with self.subTest(adapter=adapter, name=name):
                    self.assertIsInstance(value, tuple)
                    self.assertTrue(value)


class DeliveryRatesOverrideTests(SimpleTestCase):
    def test_an_override_replaces_one_value_and_keeps_the_rest(self):
        merged = load(channel_override("sms_send", provider_limit=20, manual_rate=5))

        self.assertEqual(merged["channels"]["sms_send"]["provider_limit"], 20)
        self.assertEqual(merged["channels"]["sms_send"]["manual_rate"], 5)
        self.assertEqual(merged["channels"]["sms_send"]["burst"], DEFAULTS["channels"]["sms_send"]["burst"])
        self.assertEqual(merged["channels"]["graph_send"], DEFAULTS["channels"]["graph_send"])
        self.assertEqual(DEFAULTS["channels"]["sms_send"]["provider_limit"], 1)

    def test_blank_or_missing_overrides_change_nothing(self):
        for raw in ("", "   ", "{}"):
            with self.subTest(raw=raw):
                self.assertEqual(load_delivery_rates(DEFAULTS, raw), load_delivery_rates(DEFAULTS))

    def test_lists_are_replaced_whole_and_kept_as_tuples(self):
        merged = load({"signals": {"ses": {"throttle_codes": ["Throttling"]}}})
        self.assertEqual(merged["signals"]["ses"]["throttle_codes"], ("Throttling",))

    def test_another_smtp_host_profile_or_limit_can_be_added(self):
        profiles = {"smtp.example.edu": {"daily_limit": 500}, "smtp.gmail.com": {"daily_limit": 1_500}}
        merged = load({"channels": {"smtp_send": {"host_profiles": profiles}}})

        merged_profiles = merged["channels"]["smtp_send"]["host_profiles"]
        self.assertEqual(merged_profiles["smtp.example.edu"], {"daily_limit": 500})
        self.assertEqual(merged_profiles["smtp.gmail.com"], {"daily_message_limit": 2_000, "daily_limit": 1_500})
        self.assertIn("smtp-relay.gmail.com", merged_profiles)

    def test_null_clears_an_optional_limit(self):
        merged = load(channel_override("graph_send", daily_limit=None, hourly_external_limit=None))
        self.assertIsNone(merged["channels"]["graph_send"]["daily_limit"])

    def test_unknown_or_misshapen_overrides_are_refused(self):
        cases = {
            "not json": "must be valid JSON",
            "[1, 2]": "must be a JSON object",
            '"text"': "must be a JSON object",
            '{"channels": {"sms_send": {"provider_limit": NaN}}}': "must be valid JSON",
            '{"channels": {"sms_send": {"provider_limt": 2}}}': "channels.sms_send.provider_limt is not a delivery",
            '{"channels": {"fax_send": {}}}': "channels.fax_send is not a delivery-rate setting",
            '{"tuning": {}}': "tuning is not a delivery-rate setting",
            '{"channels": {"sms_send": 5}}': "channels.sms_send must be a JSON object",
            '{"channels": {"smtp_send": {"host_profiles": {"smtp.gmail.com": {"hourly": 1}}}}}': "must set one or more",
        }
        for raw, message in cases.items():
            with self.subTest(raw=raw), self.assertRaisesMessage(ImproperlyConfigured, message):
                load_delivery_rates(DEFAULTS, raw)

    def test_the_override_is_read_from_the_environment_at_import(self):
        override = json.dumps(channel_override("graph_send", provider_limit=20, manual_rate=20))
        try:
            with patch.dict("os.environ", {"DELIVERY_RATES_OVERRIDES": override}):
                reloaded = importlib.reload(rates_settings)
            self.assertEqual(reloaded.DELIVERY_RATES["channels"]["graph_send"]["provider_limit"], 20)

            with patch.dict("os.environ", {"DELIVERY_RATES_OVERRIDES": '{"channels": {"graph_send": {"burst": 0}}}'}):
                with self.assertRaisesMessage(ImproperlyConfigured, "channels.graph_send.burst must be a whole number"):
                    importlib.reload(rates_settings)
        finally:
            with patch.dict("os.environ", {}, clear=False) as environ:
                environ.pop("DELIVERY_RATES_OVERRIDES", None)
                importlib.reload(rates_settings)
        self.assertEqual(rates_settings.DELIVERY_RATES, settings.DELIVERY_RATES)


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
