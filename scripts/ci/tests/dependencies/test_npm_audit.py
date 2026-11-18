from __future__ import annotations

import copy
import unittest
from datetime import date
from pathlib import Path

from scripts.ci.dependencies.audit_npm import (
    AuditDataError,
    exception_failures,
    root_advisories,
    validate_audit_returncode,
)

ROOT = Path(__file__).resolve().parents[4]


ADVISORY = {
    "source": 1247710,
    "name": "picomatch",
    "dependency": "picomatch",
    "title": "picomatch vulnerable to ReDoS through single-branch repeated extglobs",
    "url": "https://github.com/advisories/GHSA-fc5q-39xc-vjpf",
    "severity": "high",
    "range": "<=4.0.7",
}


def audit_report() -> dict:
    return {
        "vulnerabilities": {
            "picomatch": {
                "name": "picomatch",
                "severity": "high",
                "isDirect": False,
                "via": [copy.deepcopy(ADVISORY)],
                "effects": ["vite"],
                "nodes": ["node_modules/picomatch"],
            },
            "vite": {
                "name": "vite",
                "severity": "high",
                "isDirect": True,
                "via": ["picomatch"],
                "effects": [],
                "nodes": ["node_modules/vite"],
            },
        }
    }


def package_lock() -> dict:
    return {
        "packages": {
            "node_modules/picomatch": {"version": "4.0.7", "dev": True},
            "node_modules/vite": {"version": "8.3.8", "dev": True},
        }
    }


class NpmAuditExceptionTests(unittest.TestCase):
    def evaluate(self, report=None, lock=None, latest="4.0.7", today=date(2026, 11, 18)):
        return exception_failures(
            report or audit_report(),
            lock or package_lock(),
            {"picomatch": latest},
            today,
        )

    def test_accepts_only_the_reviewed_dev_only_dependency_chain(self) -> None:
        failures, accepted = self.evaluate()

        self.assertEqual(failures, [])
        self.assertEqual(accepted, {"GHSA-fc5q-39xc-vjpf"})

    def test_rejects_an_unlisted_advisory(self) -> None:
        report = audit_report()
        report["vulnerabilities"]["picomatch"]["via"][0]["url"] = "https://github.com/advisories/GHSA-aaaa-bbbb-cccc"

        failures, _ = self.evaluate(report=report)

        self.assertTrue(any("unaccepted advisory" in failure for failure in failures), failures)

    def test_rejects_a_runtime_dependency_path(self) -> None:
        lock = package_lock()
        lock["packages"]["node_modules/vite"].pop("dev")

        failures, _ = self.evaluate(lock=lock)

        self.assertTrue(any("not marked dev-only" in failure for failure in failures), failures)

    def test_rejects_changed_advisory_scope_or_locked_version(self) -> None:
        report = audit_report()
        report["vulnerabilities"]["picomatch"]["via"][0]["range"] = "<4.0.9"
        lock = package_lock()
        lock["packages"]["node_modules/picomatch"]["version"] = "4.0.6"

        failures, _ = self.evaluate(report=report, lock=lock)

        self.assertTrue(any("affected range changed" in failure for failure in failures), failures)
        self.assertTrue(any("reviewed picomatch 4.0.7" in failure for failure in failures), failures)

    def test_rejects_a_new_release_or_an_expired_exception(self) -> None:
        new_release_failures, _ = self.evaluate(latest="4.0.8")
        expired_failures, _ = self.evaluate(today=date(2026, 12, 19))

        self.assertTrue(any("4.0.8 is now published" in failure for failure in new_release_failures))
        self.assertTrue(any("exception expired" in failure for failure in expired_failures))

    def test_rejects_when_picomatch_becomes_direct(self) -> None:
        report = copy.deepcopy(audit_report())
        report["vulnerabilities"]["picomatch"]["isDirect"] = True

        failures, _ = self.evaluate(report=report)

        self.assertTrue(any("no longer strictly transitive" in failure for failure in failures), failures)

    def test_missing_or_rootless_dependency_graph_fails_closed(self) -> None:
        missing = audit_report()["vulnerabilities"]
        missing["vite"]["via"] = ["missing-package"]
        with self.assertRaisesRegex(AuditDataError, "missing vulnerability"):
            root_advisories("vite", missing)

        cyclic = audit_report()["vulnerabilities"]
        cyclic["picomatch"]["via"] = ["vite"]
        with self.assertRaisesRegex(AuditDataError, "no root advisory"):
            root_advisories("vite", cyclic)

    def test_dependency_cycle_is_allowed_only_when_an_advisory_root_remains(self) -> None:
        report = audit_report()
        report["vulnerabilities"]["coverage"] = {
            "name": "coverage",
            "severity": "high",
            "isDirect": True,
            "via": ["vite"],
            "effects": ["vite"],
            "nodes": ["node_modules/coverage"],
        }
        report["vulnerabilities"]["vite"]["via"] = ["coverage", "picomatch"]

        roots = root_advisories("coverage", report["vulnerabilities"])

        self.assertEqual(roots, {("GHSA-fc5q-39xc-vjpf", "picomatch", "<=4.0.7")})

    def test_unexpected_audit_exit_codes_fail_closed(self) -> None:
        validate_audit_returncode(0, False)
        validate_audit_returncode(1, True)
        with self.assertRaisesRegex(AuditDataError, "exited 2; expected 1"):
            validate_audit_returncode(2, True)
        with self.assertRaisesRegex(AuditDataError, "exited 1; expected 0"):
            validate_audit_returncode(1, False)


class NpmAuditWorkflowTests(unittest.TestCase):
    def test_ci_and_scheduled_audits_share_the_narrow_validator(self) -> None:
        command = "run: python ../scripts/ci/dependencies/audit_npm.py"
        for relative in (".github/workflows/ci.yml", ".github/workflows/dependency-audit.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertEqual(workflow.count(command), 1)
                self.assertNotIn("run: npm audit --audit-level", workflow)


if __name__ == "__main__":
    unittest.main()
