"""Regression coverage for production signing-key initialization."""

import os
import secrets
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from apps.authn.services.send_verification.config import require_ready
from apps.authn.services.send_verification.exceptions import SendVerificationUnavailable
from apps.core.models import SendVerificationConfig

_PRODUCTION_POLICY = {
    "SEND_VERIFICATION_MODE": None,
    "SEND_VERIFICATION_HMAC_SECRET": None,
    "SEND_VERIFICATION_HMAC_KEY_SECRET": None,
    "SEND_VERIFICATION_SMS_DAILY_LIMIT": None,
}


def initialize():
    output = StringIO()
    call_command("initialize_send_verification", stdout=output)
    return output.getvalue()


@override_settings(**_PRODUCTION_POLICY)
class InitializeSendVerificationTests(TestCase):
    def test_empty_database_becomes_ready_for_both_channels_without_disclosing_key(self):
        with self.assertRaises(SendVerificationUnavailable):
            require_ready()

        output = initialize()

        config = SendVerificationConfig.objects.get()
        self.assertTrue(config.is_active)
        self.assertEqual(config.mode, "observe")
        self.assertGreaterEqual(len(config.hmac_secret), 64)
        self.assertNotIn(config.hmac_secret, output)
        self.assertEqual(require_ready().hmac_secret, config.hmac_secret)
        self.assertEqual(require_ready(for_sms=True).hmac_secret, config.hmac_secret)

    def test_rerun_preserves_key_policy_and_updated_timestamp(self):
        initialize()
        original = SendVerificationConfig.objects.values().get()

        with patch("apps.core.management.commands.initialize_send_verification.secrets.token_urlsafe") as generate:
            initialize()

        generate.assert_not_called()
        self.assertEqual(SendVerificationConfig.objects.values().get(), original)

    def test_repairs_whitespace_key_while_preserving_pause_rotation_and_policy(self):
        config = SendVerificationConfig.objects.create(
            name="Existing paused policy",
            is_active=True,
            mode="pause",
            hmac_secret=" \t ",
            hmac_key_secret="keep-optional-key",
            hmac_secret_previous="keep-previous-key",
            hmac_key_secret_previous="keep-previous-optional-key",
            key_version=7,
            cost=9000,
            challenge_ttl_seconds=180,
            destination_hourly_limit=3,
            destination_cooldown_seconds=120,
            sms_daily_limit=20,
        )
        before = SendVerificationConfig.objects.values().get(pk=config.pk)

        output = initialize()

        after = SendVerificationConfig.objects.values().get(pk=config.pk)
        self.assertGreaterEqual(len(after["hmac_secret"]), 64)
        self.assertNotIn(after["hmac_secret"], output)
        for field in before.keys() - {"hmac_secret", "updated_at"}:
            self.assertEqual(after[field], before[field], field)

    def test_existing_nonempty_key_is_never_rotated(self):
        SendVerificationConfig.objects.create(is_active=True, hmac_secret="existing-signing-key", mode="enforce")
        original = SendVerificationConfig.objects.values().get()

        initialize()

        self.assertEqual(SendVerificationConfig.objects.values().get(), original)

    def test_inactive_only_configuration_is_not_activated_or_replaced(self):
        SendVerificationConfig.objects.create(name="Deliberately disabled", is_active=False, hmac_secret="retained")
        original = SendVerificationConfig.objects.values().get()

        initialize()

        self.assertEqual(SendVerificationConfig.objects.count(), 1)
        self.assertEqual(SendVerificationConfig.objects.values().get(), original)
        with self.assertRaises(SendVerificationUnavailable):
            require_ready()

    def test_explicit_signing_key_override_leaves_database_untouched(self):
        for override in ("environment-key", "", " \t "):
            with (
                self.subTest(override=bool(override.strip())),
                override_settings(SEND_VERIFICATION_HMAC_SECRET=override),
            ):
                output = initialize()
                self.assertFalse(SendVerificationConfig.objects.exists())
                if override.strip():
                    self.assertEqual(require_ready().hmac_secret, override)
                    self.assertNotIn(override, output)
                else:
                    with self.assertRaises(SendVerificationUnavailable):
                        require_ready()


@skipUnless(connection.vendor == "postgresql", "Concurrent startup requires PostgreSQL transaction locks.")
@override_settings(**_PRODUCTION_POLICY)
class ConcurrentSendVerificationInitializationTests(TransactionTestCase):
    def test_concurrent_startup_generates_and_retains_one_key(self):
        start = threading.Barrier(2)

        def boot():
            close_old_connections()
            try:
                start.wait(timeout=10)
                initialize()
                return SendVerificationConfig.objects.get(is_active=True).hmac_secret
            finally:
                close_old_connections()

        with patch(
            "apps.core.management.commands.initialize_send_verification.secrets.token_urlsafe",
            wraps=secrets.token_urlsafe,
        ) as generate:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: boot(), range(2)))

        generate.assert_called_once_with(48)
        self.assertEqual(SendVerificationConfig.objects.count(), 1)
        self.assertEqual(results, [SendVerificationConfig.objects.get().hmac_secret] * 2)


class SendVerificationStartupTests(SimpleTestCase):
    def _boot(self, *, fail_command=""):
        entrypoint = Path(__file__).resolve().parents[4] / "entrypoint.sh"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = root / "calls"
            bin_directory = root / "bin"
            bin_directory.mkdir()
            (root / "staticfiles").mkdir()
            (root / "staticfiles" / "fixture.txt").write_text("present", encoding="utf-8")
            for executable in ("python", "uvicorn"):
                stub = bin_directory / executable
                stub.write_text(
                    "#!/bin/sh\n"
                    f'printf "%s\\n" "{executable} $*" >> "$STARTUP_TEST_CALLS"\n'
                    'if [ "$1" = "manage.py" ] && [ "$2" = "$STARTUP_TEST_FAIL_COMMAND" ]; then exit 1; fi\n',
                    encoding="utf-8",
                )
                stub.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{bin_directory}{os.pathsep}{os.environ.get('PATH', '')}",
                "ENSURE_DEFAULT_ADMIN": "false",
                "STARTUP_TEST_CALLS": str(calls),
                "STARTUP_TEST_FAIL_COMMAND": fail_command,
            }
            result = subprocess.run(["sh", str(entrypoint)], cwd=root, env=env, capture_output=True, text=True)
            return result, calls.read_text(encoding="utf-8").splitlines()

    def test_initialization_and_both_channel_policy_checks_precede_traffic(self):
        result, calls = self._boot()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls[:3],
            [
                "python manage.py migrate --noinput",
                "python manage.py initialize_send_verification",
                "python manage.py verify_service_configs --strict --send-verification-only --require-sms",
            ],
        )
        self.assertTrue(calls[3].startswith("uvicorn "))

    def test_failed_initialization_or_readiness_prevents_accepting_traffic(self):
        for command in ("initialize_send_verification", "verify_service_configs"):
            with self.subTest(command=command):
                result, calls = self._boot(fail_command=command)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(call.startswith("uvicorn ") for call in calls))
