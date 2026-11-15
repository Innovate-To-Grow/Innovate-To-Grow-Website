from __future__ import annotations

import re
import unittest

from scripts.ci.tool_versions.pins import PIN_GROUPS, collect_pins, mismatches
from scripts.ci.tool_versions.sources import PinError, Regex

from .pin_fixtures import (
    CI,
    DEPENDENCY_AUDIT,
    DRIFTS,
    EXPECTED,
    IMAGE,
    PACKAGE_LOCK,
    PRE_COMMIT,
    REPOSITORY_ROOT,
    fake_repository,
    replace_once,
)


class CollectPinsTests(unittest.TestCase):
    def test_aligned_fixture_reads_every_group_without_mismatches(self) -> None:
        with fake_repository() as root:
            pins = collect_pins(root)

        self.assertEqual(list(pins), list(EXPECTED))
        for group, (value, sources) in EXPECTED.items():
            with self.subTest(group=group):
                self.assertEqual([pin_value for _, pin_value in pins[group]], [value] * sources)
        self.assertEqual(mismatches(pins), [])

    def test_each_drift_is_reported_for_its_group_only(self) -> None:
        for group, path, old, new, aligned, drifted in DRIFTS:
            with self.subTest(group=group, path=path), fake_repository() as root:
                replace_once(root, path, old, new)

                problems = mismatches(collect_pins(root))

                self.assertEqual([problem.split(":")[0] for problem in problems], [group], problems)
                self.assertIn(f"{drifted} ({path}", problems[0])
                self.assertIn(f"{aligned} (", problems[0])

    def test_audits_may_accept_no_advisories_but_must_agree(self) -> None:
        with fake_repository() as root:
            replace_once(root, CI, " --ignore-vuln GHSA-aaaa-bbbb-cccc --ignore-vuln PYSEC-2026-1", "")
            replace_once(root, DEPENDENCY_AUDIT, " --ignore-vuln PYSEC-2026-1 --ignore-vuln GHSA-aaaa-bbbb-cccc", "")
            pins = collect_pins(root)
            self.assertEqual([value for _, value in pins["pip-audit-ignores"]], ["none", "none"])
            self.assertEqual(mismatches(pins), [])

            # The likely slip: a new advisory accepted in ci.yml only.
            replace_once(root, CI, "- run: pip-audit\n", "- run: pip-audit --ignore-vuln GHSA-dddd-eeee-ffff\n")
            problems = mismatches(collect_pins(root))

        self.assertEqual(problems, [f"pip-audit-ignores: GHSA-dddd-eeee-ffff ({CI}) vs none ({DEPENDENCY_AUDIT})"])

    def test_labels_name_the_lines_each_value_was_found_on(self) -> None:
        with fake_repository() as root:
            replace_once(root, CI, "postgres:16", "postgres:17")
            lines = (root / CI).read_text(encoding="utf-8").splitlines()
            (problem,) = mismatches(collect_pins(root))

        def lines_with(text: str) -> str:
            return ",".join(str(number) for number, line in enumerate(lines, 1) if text in line)

        self.assertTrue(problem.startswith(f"postgres: 17 ({CI}:{lines_with('postgres:17')}) vs 16 ({CI}:"), problem)
        self.assertTrue(problem.endswith(f"vs 16 ({CI}:{lines_with('postgres:16')})"), problem)

    def test_a_source_that_finds_nothing_names_its_file_and_target(self) -> None:
        cases = (
            ("scripts/pre-commit/gitleaks-protect.sh", "${GITLEAKS_VERSION:-8.21.2}", "8.21.2", "GITLEAKS_VERSION"),
            # Only literals are pins: a `${{ env.* }}` expression leaves the file without one.
            (
                ".github/workflows/deploy-frontend.yml",
                'node-version: "22.22.2"',
                "node-version: ${{ env.NODE_VERSION }}",
                "node-version",
            ),
            (PRE_COMMIT, "astral-sh/ruff-pre-commit", "charliermarsh/ruff-pre-commit", "astral-sh/ruff-pre-commit"),
            (PRE_COMMIT, '"bandit[toml]==1.7.10"', '"bandit[toml]"', "bandit"),
            (PACKAGE_LOCK, '"node_modules/@playwright/test"', '"node_modules/playwright"', "@playwright/test"),
        )
        for path, old, new, looked_for in cases:
            with self.subTest(path=path, looked_for=looked_for), fake_repository() as root:
                replace_once(root, path, old, new)

                with self.assertRaises(PinError) as caught:
                    collect_pins(root)

                self.assertTrue(str(caught.exception).startswith(f"{path}: "), caught.exception)
                self.assertIn(looked_for, str(caught.exception))

    def test_fewer_matches_than_the_minimum_is_a_pin_error(self) -> None:
        cases = (
            (CI, "image: postgres:16", "image: postgres:latest", "postgres", "found 3"),
            (CI, f'"{IMAGE}"', '"mcr.microsoft.com/playwright:v1.64.0-noble"', "sha256", "found 1"),
            (CI, '"pip-audit==2.7.3"', "pip-audit", "pip-audit", "found 0"),
            # An image scan that stops pinning a literal version drops out of the trivy group.
            (CI, 'TRIVY_VERSION: "0.70.0"', "TRIVY_VERSION: ${{ env.TRIVY }}", "TRIVY_VERSION", "found 1"),
        )
        for path, old, new, looked_for, found in cases:
            with self.subTest(path=path, looked_for=looked_for), fake_repository() as root:
                replace_once(root, path, old, new)

                with self.assertRaises(PinError) as caught:
                    collect_pins(root)

                message = str(caught.exception)
                self.assertTrue(message.startswith(f"{path}: expected at least "), message)
                self.assertIn(looked_for, message)
                self.assertTrue(message.endswith(found), message)

    def test_a_missing_file_is_a_pin_error(self) -> None:
        with fake_repository() as root:
            (root / ".github/workflows/deploy-archive.yml").unlink()

            with self.assertRaisesRegex(PinError, r"^\.github/workflows/deploy-archive\.yml: cannot read"):
                collect_pins(root)

    def test_each_repository_source_declares_its_exact_match_count(self) -> None:
        # A minimum below the real count lets one occurrence be rewritten (say to
        # postgres:latest) and silently drop out of the check while the rest still
        # agree. Keeping each minimum equal to the count closes that gap.
        for group, sources in PIN_GROUPS.items():
            for source in sources:
                if not isinstance(source, Regex) or source.as_set:
                    continue
                with self.subTest(group=group, path=source.path, regex=source.regex):
                    text = (REPOSITORY_ROOT / source.path).read_text(encoding="utf-8")
                    self.assertEqual(len(re.findall(source.regex, text, re.MULTILINE)), source.minimum)


if __name__ == "__main__":
    unittest.main()
