from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from security_exceptions import arguments, load_policy


class SecurityExceptionPolicyTests(unittest.TestCase):
    def _policy(self, exceptions):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "policy.json"
        path.write_text(
            json.dumps({"schema_version": 1, "exceptions": exceptions}),
            encoding="utf-8",
        )
        return path

    def _entry(self, **overrides):
        entry = {
            "scanner": "pip-audit",
            "id": "GHSA-abcd-1234-5678",
            "owner": "@security-team",
            "rationale": "No fixed transitive release is currently available.",
            "expires_on": (date.today() + timedelta(days=30)).isoformat(),
        }
        entry.update(overrides)
        return entry

    def test_valid_policy_renders_scanner_arguments(self):
        entries = load_policy(self._policy([self._entry()]))
        self.assertEqual(
            arguments(entries, "pip-audit"),
            ["--ignore-vuln", "GHSA-abcd-1234-5678"],
        )

    def test_expired_exception_is_rejected(self):
        path = self._policy([self._entry(expires_on=(date.today() - timedelta(days=1)).isoformat())])
        with self.assertRaisesRegex(ValueError, "expired"):
            load_policy(path)

    def test_exception_requires_owner_and_substantive_rationale(self):
        path = self._policy([self._entry(owner="team", rationale="temporary")])
        with self.assertRaisesRegex(ValueError, "owner"):
            load_policy(path)

    def test_exception_cannot_outlive_ninety_days(self):
        path = self._policy([self._entry(expires_on=(date.today() + timedelta(days=91)).isoformat())])
        with self.assertRaisesRegex(ValueError, "at most 90 days"):
            load_policy(path)
