"""DELIVERY_RATES: the per-channel seeds, the env overrides deep-merged into them, and the validation at import."""

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
from config.settings.base.integrations.delivery_rates.validation import load_delivery_rates

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
        # OIT's recipients-per-message limit; seeds MicrosoftGraphProviderConfig.max_recipients_per_message.
        self.assertEqual(graph["max_recipients_per_message"], 500)
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
        text = Path(rates_settings.defaults.channels.__file__).read_text(encoding="utf-8")
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
