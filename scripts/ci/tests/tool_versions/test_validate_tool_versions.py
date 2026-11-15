from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

from scripts.ci.tool_versions.cli import main
from scripts.ci.tool_versions.pins import collect_pins, mismatches

from .pin_fixtures import CI, IGNORED, PACKAGE_LOCK, REPOSITORY_ROOT, fake_repository, replace_once


class MainTests(unittest.TestCase):
    def run_main(self, root: Path) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--root", str(root)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_aligned_checkout_prints_one_summary_line(self) -> None:
        with fake_repository() as root:
            code, stdout, stderr = self.run_main(root)

        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(stdout.count("\n"), 1)
        self.assertTrue(stdout.startswith("Tool versions aligned: ruff=0.17.2, bandit=1.7.10, gitleaks=8.21.2, "))
        self.assertIn(f", pip-audit-ignores={IGNORED}\n", stdout)

    def test_drift_fails_naming_the_group_and_both_values(self) -> None:
        with fake_repository() as root:
            replace_once(root, CI, "pw-v1.64.0-noble", "pw-v1.62.1-noble")
            code, stdout, stderr = self.run_main(root)

        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("playwright: 1.64.0 (", stderr)
        self.assertIn(f" vs 1.62.1 ({CI}:", stderr)

    def test_pin_error_fails_with_its_message(self) -> None:
        with fake_repository() as root:
            (root / PACKAGE_LOCK).unlink()
            code, stdout, stderr = self.run_main(root)

        self.assertEqual((code, stdout), (1, ""))
        self.assertIn(f"{PACKAGE_LOCK}: cannot read", stderr)


class RepositoryPinsTests(unittest.TestCase):
    def test_repository_pins_are_aligned(self) -> None:
        self.assertEqual(mismatches(collect_pins(REPOSITORY_ROOT)), [])


if __name__ == "__main__":
    unittest.main()
