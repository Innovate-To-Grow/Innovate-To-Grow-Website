from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.ci.check_coverage_totals import check_coverage, main


def report(*, covered_lines: int = 99, statements: int = 100, covered_branches: int = 49, branches: int = 50):
    return {
        "totals": {
            "covered_lines": covered_lines,
            "num_statements": statements,
            "covered_branches": covered_branches,
            "num_branches": branches,
        }
    }


class CheckCoverageTotalsTests(unittest.TestCase):
    def test_accepts_exact_independent_boundaries(self):
        self.assertEqual(check_coverage(report(), 99, 98), (99, 98))

    def test_rejects_line_regression_even_when_branch_coverage_is_high(self):
        with self.assertRaisesRegex(ValueError, "line coverage 98.00%"):
            check_coverage(report(covered_lines=98, covered_branches=50), 99, 98)

    def test_rejects_branch_regression_even_when_line_coverage_is_high(self):
        with self.assertRaisesRegex(ValueError, "branch coverage 96.00%"):
            check_coverage(report(covered_lines=100, covered_branches=48), 99, 98)

    def test_treats_zero_statement_and_branch_reports_as_fully_covered(self):
        self.assertEqual(
            check_coverage(report(covered_lines=0, statements=0, covered_branches=0, branches=0), 100, 100),
            (100, 100),
        )

    def test_rejects_invalid_counts(self):
        with self.assertRaisesRegex(ValueError, "0 <= covered <= total"):
            check_coverage(report(covered_lines=101), 0, 0)

    def test_main_reports_malformed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.json"
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(main([str(path), "--line-floor", "99", "--branch-floor", "98"]), 1)

    def test_main_accepts_valid_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.json"
            path.write_text(json.dumps(report()), encoding="utf-8")
            self.assertEqual(main([str(path), "--line-floor", "99", "--branch-floor", "98"]), 0)


if __name__ == "__main__":
    unittest.main()
