from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.authn.services.send_verification.rules.exceptions import SendVerificationUnavailable
from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    SendVerificationConfig,
)
from apps.core.tests.commands.verify.test_verify_service_configs import PRODUCTION_SEND_VERIFICATION_SETTINGS


@override_settings(**PRODUCTION_SEND_VERIFICATION_SETTINGS)
class VerifySendVerificationReadinessCommandTest(TestCase):
    def setUp(self):
        SendVerificationConfig.objects.all().delete()
        EmailServiceConfig.objects.create(
            name="Production", is_active=True, provider="ses", from_email="i2g@g.ucmerced.edu"
        )
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            sms_from_number="+12065550000",
        )

    def _config(self, **overrides):
        values = {
            "name": "Production",
            "is_active": True,
            "mode": "observe",
            "hmac_secret": "test-readiness-signing-key",
        }
        values.update(overrides)
        return SendVerificationConfig.objects.create(**values)

    def _run(self, *args):
        output = StringIO()
        call_command("verify_service_configs", *args, stdout=output)
        return output.getvalue()

    def test_missing_effective_signing_secret_fails_strict(self):
        with self.assertRaises(CommandError):
            self._run("--strict")

    def test_missing_effective_signing_secret_reports_failure_without_strict(self):
        output = self._run()
        self.assertIn("FAIL: Effective send verification is not ready.", output)
        self.assertNotIn("Service config verification passed.", output)

    def test_blank_database_signing_secret_fails_in_observe_mode(self):
        for secret in ("", " \t\n"):
            with self.subTest(secret=repr(secret)):
                self._config(hmac_secret=secret)
                with self.assertRaises(CommandError):
                    self._run("--strict")
                SendVerificationConfig.objects.all().delete()

    def test_active_database_policy_passes_without_environment_secrets(self):
        self._config()
        output = self._run("--strict")
        self.assertIn("SendVerificationConfig: OK (effective mode: observe)", output)
        self.assertIn("Service config verification passed.", output)

    def test_inactive_database_secret_does_not_satisfy_readiness(self):
        self._config(is_active=False)
        with self.assertRaises(CommandError):
            self._run("--strict")

    @override_settings(SEND_VERIFICATION_HMAC_SECRET="effective-environment-signing-key")
    def test_environment_signing_secret_passes_without_database_config(self):
        output = self._run("--strict")
        self.assertIn("SendVerificationConfig: OK (effective mode: observe)", output)
        self.assertFalse(SendVerificationConfig.objects.exists())
        self.assertNotIn("effective-environment-signing-key", output)

    def test_explicit_empty_environment_secret_overrides_valid_database_secret(self):
        self._config()
        for secret in ("", " \t\n"):
            with self.subTest(secret=repr(secret)), override_settings(SEND_VERIFICATION_HMAC_SECRET=secret):
                with self.assertRaises(CommandError):
                    self._run("--strict")

    def test_invalid_effective_policy_fails_strict(self):
        self._config()
        for setting, value in (
            ("SEND_VERIFICATION_MODE", "invalid-mode"),
            ("SEND_VERIFICATION_ALGORITHM", "invalid-algorithm"),
            ("SEND_VERIFICATION_COST", "invalid-cost"),
            ("SEND_VERIFICATION_TTL_SECONDS", 0),
            ("SEND_VERIFICATION_SMS_DAILY_LIMIT", -1),
        ):
            with self.subTest(setting=setting), override_settings(**{setting: value}):
                with self.assertRaises(CommandError):
                    self._run("--strict")

    def test_pause_is_preserved_as_warning_even_with_missing_secret(self):
        config = self._config(mode="pause", hmac_secret="")
        with override_settings(SEND_VERIFICATION_MODE="enforce"):
            output = self._run("--strict", "--require-sms")
        self.assertIn("SendVerificationConfig: PAUSED", output)
        self.assertIn("WARN: Verification-code sending is paused by the effective policy.", output)
        self.assertIn("Service config verification passed.", output)
        config.refresh_from_db()
        self.assertEqual(config.mode, "pause")
        self.assertEqual(config.hmac_secret, "")

    def test_enforced_sms_cap_is_required_only_when_sms_is_required(self):
        config = self._config(mode="enforce", sms_daily_limit=None)
        self.assertIn("Service config verification passed.", self._run("--strict"))
        with self.assertRaises(CommandError):
            self._run("--strict", "--require-sms")
        config.sms_daily_limit = 10
        config.save(update_fields=["sms_daily_limit"])
        self.assertIn("Service config verification passed.", self._run("--strict", "--require-sms"))

    @override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT="0")
    def test_explicit_zero_sms_cap_overrides_database_limit(self):
        self._config(mode="enforce", sms_daily_limit=10)
        with self.assertRaises(CommandError):
            self._run("--strict", "--require-sms")

    def test_observe_does_not_require_sms_cap(self):
        self._config(mode="observe", sms_daily_limit=None)
        self.assertIn("Service config verification passed.", self._run("--strict", "--require-sms"))

    def test_failure_output_does_not_include_exception_details(self):
        with patch(
            "apps.core.management.commands.verify_service_configs.require_ready",
            side_effect=SendVerificationUnavailable("sensitive-policy-value"),
        ):
            output = self._run()
        self.assertIn("FAIL: Effective send verification is not ready.", output)
        self.assertNotIn("sensitive-policy-value", output)

    def test_policy_only_checks_effective_readiness_without_loading_providers(self):
        self._config(mode="enforce", sms_daily_limit=10)
        with (
            patch(
                "apps.core.management.commands.verify_service_configs.EmailServiceConfig.load",
                side_effect=AssertionError("Policy-only verification must not load email credentials."),
            ),
            patch(
                "apps.core.management.commands.verify_service_configs.AWSCredentialConfig.load",
                side_effect=AssertionError("Policy-only verification must not load AWS credentials."),
            ),
        ):
            output = self._run("--strict", "--send-verification-only", "--require-sms")
        self.assertIn("SendVerificationConfig: OK (effective mode: enforce)", output)
        self.assertNotIn("AWSCredentialConfig:", output)

    def test_policy_only_still_rejects_missing_signing_secret(self):
        with self.assertRaises(CommandError):
            self._run("--strict", "--send-verification-only", "--require-sms")

    def test_policy_only_preserves_pause(self):
        self._config(mode="pause", hmac_secret="", sms_daily_limit=None)
        output = self._run("--strict", "--send-verification-only", "--require-sms")
        self.assertIn("SendVerificationConfig: PAUSED", output)
        self.assertIn("Service config verification passed.", output)
