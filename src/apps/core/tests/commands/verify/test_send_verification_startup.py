import os
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase


class SendVerificationStartupTests(SimpleTestCase):
    def _boot(self, *, fail_command="", migrate=False):
        entrypoint = Path(__file__).resolve().parents[5] / "docker" / "entrypoint.sh"
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
                "RUN_DATABASE_MIGRATIONS": "true" if migrate else "false",
                "STARTUP_TEST_CALLS": str(calls),
                "STARTUP_TEST_FAIL_COMMAND": fail_command,
            }
            result = subprocess.run(["sh", str(entrypoint)], cwd=root, env=env, capture_output=True, text=True)
            return result, calls.read_text(encoding="utf-8").splitlines()

    def test_initialization_and_both_channel_policy_checks_precede_traffic(self):
        result, calls = self._boot()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            calls[:2],
            [
                "python manage.py initialize_send_verification",
                "python manage.py verify_service_configs --strict --send-verification-only --require-sms",
            ],
        )
        self.assertTrue(calls[2].startswith("uvicorn "))
        self.assertFalse(any("manage.py migrate " in call for call in calls))

    def test_disposable_smoke_database_can_opt_in_to_migration(self):
        result, calls = self._boot(migrate=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[0], "python manage.py migrate --noinput")

    def test_failed_initialization_or_readiness_prevents_accepting_traffic(self):
        for command in ("initialize_send_verification", "verify_service_configs"):
            with self.subTest(command=command):
                result, calls = self._boot(fail_command=command)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(call.startswith("uvicorn ") for call in calls))
