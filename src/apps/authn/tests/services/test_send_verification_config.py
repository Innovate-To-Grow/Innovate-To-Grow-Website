"""Regression coverage for runtime/admin send policy precedence and fail-closed parsing."""

import runpy
from unittest.mock import patch

from django.contrib.admin import AdminSite
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.authn.services.send_verification.config import load_settings, require_ready
from apps.authn.services.send_verification.exceptions import SendPaused, SendVerificationUnavailable
from apps.core.admin.service_credentials.send_verification import (
    SendVerificationConfigAdmin,
    SendVerificationConfigForm,
)
from apps.core.models import SendVerificationConfig
from config.settings.components.integrations import api

INHERIT_SETTINGS = {name: None for name in vars(api) if name.startswith("SEND_VERIFICATION_")} | {
    "SEND_VERIFICATION_TEST_AUTOSOLVE": False
}


@override_settings(**INHERIT_SETTINGS)
class SendVerificationConfigTests(TestCase):
    def setUp(self):
        cache.clear()
        self.config = SendVerificationConfig.objects.create(
            name="Policy regression",
            is_active=True,
            mode="enforce",
            hmac_secret="private-signing-secret",
            hmac_key_secret="private-key-secret",
            cost=700,
            challenge_ttl_seconds=120,
            destination_hourly_limit=3,
            destination_cooldown_seconds=180,
            sms_daily_limit=40,
        )

    def test_active_admin_policy_is_effective_without_explicit_overrides(self):
        effective = require_ready(for_sms=True)
        self.assertEqual(effective.mode, "enforce")
        self.assertEqual(effective.cost, 700)
        self.assertEqual(effective.ttl_seconds, 120)
        self.assertEqual(effective.destination_hourly_limit, 3)
        self.assertEqual(effective.destination_cooldown_seconds, 180)
        self.assertEqual(effective.sms_daily_limit, 40)
        self.assertEqual(effective.hmac_secret, "private-signing-secret")
        self.assertEqual(effective.sources["mode"], "Active database configuration: mode")

    @override_settings(
        SEND_VERIFICATION_MODE="observe",
        SEND_VERIFICATION_COST=10,
        SEND_VERIFICATION_TTL_SECONDS=90,
        SEND_VERIFICATION_DESTINATION_HOURLY_LIMIT=5,
        SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=0,
        SEND_VERIFICATION_SMS_DAILY_LIMIT=1000,
    )
    def test_explicit_local_test_settings_override_database(self):
        effective = require_ready(for_sms=True)
        self.assertEqual(effective.mode, "observe")
        self.assertEqual(effective.cost, 10)
        self.assertEqual(effective.ttl_seconds, 90)
        self.assertEqual(effective.destination_hourly_limit, 5)
        self.assertEqual(effective.destination_cooldown_seconds, 0)
        self.assertEqual(effective.sms_daily_limit, 1000)
        self.assertEqual(effective.sources["cost"], "Django settings: SEND_VERIFICATION_COST")

    def test_database_pause_wins_over_explicit_modes_including_invalid_mode(self):
        self.config.mode = "pause"
        self.config.save()
        for mode in ("observe", "enforce", "invalid"):
            with self.subTest(mode=mode), override_settings(SEND_VERIFICATION_MODE=mode):
                self.assertEqual(load_settings().mode, "pause")
                with self.assertRaises(SendPaused):
                    require_ready()

    @override_settings(SEND_VERIFICATION_MODE="pause")
    def test_explicit_pause_wins_over_database_enforce(self):
        with self.assertRaises(SendPaused):
            require_ready()

    def test_inactive_database_values_and_secrets_are_not_used(self):
        self.config.is_active = False
        self.config.save()
        effective = load_settings()
        self.assertEqual(effective.mode, "observe")
        self.assertEqual(effective.cost, 5000)
        self.assertEqual(effective.ttl_seconds, 300)
        self.assertEqual(effective.destination_hourly_limit, 10)
        self.assertEqual(effective.destination_cooldown_seconds, 60)
        self.assertIsNone(effective.sms_daily_limit)
        self.assertEqual(effective.hmac_secret, "")
        self.assertEqual(effective.sources["mode"], "Default")
        with self.assertRaises(SendVerificationUnavailable):
            require_ready()

    @override_settings(SEND_VERIFICATION_HMAC_SECRET="")
    def test_empty_explicit_secret_does_not_fall_back_to_database(self):
        with self.assertRaises(SendVerificationUnavailable):
            require_ready()

    def test_zero_sms_override_clears_database_cap_and_blocks_enforced_sms(self):
        for value in (0, "0"):
            with self.subTest(value=value), override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=value):
                self.assertIsNone(load_settings().sms_daily_limit)
                with self.assertRaises(SendVerificationUnavailable):
                    require_ready(for_sms=True)

    def test_invalid_effective_values_fail_closed_without_fallback(self):
        invalid = {
            "MODE": ("", "enfroce", 12),
            "ALGORITHM": ("", "SHA-256"),
            "COST": ("bad", "", 0, -1, 1.5, True),
            "TTL_SECONDS": (29, -1, "bad"),
            "DESTINATION_HOURLY_LIMIT": (0, -1, "bad"),
            "DESTINATION_COOLDOWN_SECONDS": (-1, "bad"),
            "SMS_DAILY_LIMIT": (-1, "", "bad"),
            "MAX_PAYLOAD_BYTES": (0, -1, "bad"),
            "IDEMPOTENCY_TTL_SECONDS": (0, -1),
            "RETENTION_DAYS": (0, -1),
            "CHALLENGE_CACHE_WINDOW_SECONDS": (0, "bad"),
            "CHALLENGE_CACHE_LIMIT": (0, "bad"),
        }
        for name, values in invalid.items():
            for value in values:
                with self.subTest(name=name, value=value), override_settings(**{f"SEND_VERIFICATION_{name}": value}):
                    with self.assertRaises(SendVerificationUnavailable):
                        load_settings()

    def test_invalid_saved_policy_fails_closed_if_it_bypassed_admin_validation(self):
        for field, value in (("mode", "invalid"), ("algorithm", "invalid"), ("cost", 0)):
            original = getattr(self.config, field)
            with self.subTest(field=field):
                SendVerificationConfig.objects.filter(pk=self.config.pk).update(**{field: value})
                with self.assertRaises(SendVerificationUnavailable):
                    load_settings()
                SendVerificationConfig.objects.filter(pk=self.config.pk).update(**{field: original})

    @override_settings(SEND_VERIFICATION_MODE="enfroce")
    def test_invalid_mode_returns_503_without_minting_a_challenge(self):
        client = APIClient()
        response = client.post(
            "/authn/send-verification/challenge/",
            {"operation": "login.request_code", "email": "member@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "verification_unavailable")

    def production_settings(self, **overrides):
        environment = {
            "DJANGO_SECRET_KEY": "test-only-secret",
            "DJANGO_ALLOWED_HOSTS": "example.invalid",
            "BACKEND_URL": "https://example.invalid",
            "DB_NAME": "unused",
            "DB_USER": "unused",
            "DB_PASSWORD": "unused",
            "DB_HOST": "localhost",
            "AWS_STORAGE_BUCKET_NAME": "unused-test-bucket",
        } | overrides
        with patch.dict("os.environ", environment, clear=True):
            values = runpy.run_module("config.settings.components.production", run_name="__config_regression__")
        return {name: value for name, value in values.items() if name.startswith("SEND_VERIFICATION_")}

    def test_production_without_env_inherits_admin_policy(self):
        with override_settings(**self.production_settings()):
            self.assertEqual(require_ready().mode, "enforce")
            self.assertEqual(require_ready().cost, 700)
            self.assertEqual(require_ready().destination_cooldown_seconds, 180)

    def test_production_env_overrides_are_applied_and_identified(self):
        overrides = {"SEND_VERIFICATION_MODE": "observe", "SEND_VERIFICATION_COST": "800"}
        with override_settings(**self.production_settings(**overrides)), patch.dict("os.environ", overrides):
            effective = require_ready()
            self.assertEqual(effective.mode, "observe")
            self.assertEqual(effective.cost, 800)
            self.assertEqual(effective.sources["cost"], "Environment: SEND_VERIFICATION_COST")

    def test_production_preserves_malformed_env_to_fail_closed(self):
        for overrides in ({"SEND_VERIFICATION_MODE": ""}, {"SEND_VERIFICATION_COST": "bad"}):
            with self.subTest(overrides=overrides), override_settings(**self.production_settings(**overrides)):
                with self.assertRaises(SendVerificationUnavailable):
                    require_ready()

    def test_admin_shows_effective_policy_and_sources_without_exposing_secrets(self):
        model_admin = SendVerificationConfigAdmin(SendVerificationConfig, AdminSite())
        with override_settings(SEND_VERIFICATION_COST=950):
            display = str(model_admin.effective_configuration(self.config))
        self.assertIn("enforce", display)
        self.assertIn("950", display)
        self.assertIn("Django settings: SEND_VERIFICATION_COST", display)
        self.assertIn("Active database configuration: mode", display)
        self.assertIn("Configured", display)
        self.assertNotIn(self.config.hmac_secret, display)
        self.assertNotIn(self.config.hmac_key_secret, display)

    @override_settings(SEND_VERIFICATION_COST="bad")
    def test_admin_explains_invalid_effective_policy(self):
        model_admin = SendVerificationConfigAdmin(SendVerificationConfig, AdminSite())
        display = str(model_admin.effective_configuration(self.config))
        self.assertIn("protected sends are blocked", display)
        self.assertNotIn(self.config.hmac_secret, display)

    def test_admin_rejects_unsupported_algorithm_and_unsafe_numeric_policy(self):
        data = {name: getattr(self.config, name) for name in SendVerificationConfigForm.Meta.fields}
        for field, value in (
            ("algorithm", "invalid"),
            ("cost", 0),
            ("challenge_ttl_seconds", 29),
            ("destination_hourly_limit", 0),
        ):
            with self.subTest(field=field):
                form = SendVerificationConfigForm(data={**data, field: value}, instance=self.config)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
