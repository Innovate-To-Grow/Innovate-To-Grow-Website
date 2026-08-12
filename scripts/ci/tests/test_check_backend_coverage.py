import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.ci.check_backend_coverage import ConfigurationError, check_coverage, main, parse_floors


def report(*, lines=(8, 10), branches=(3, 4), app="projects"):
    return {
        "meta": {"branch_coverage": True},
        "files": {
            f"src/apps/{app}/one.py": {
                "summary": {
                    "covered_lines": lines[0],
                    "num_statements": lines[1],
                    "covered_branches": branches[0],
                    "num_branches": branches[1],
                }
            }
        },
    }


class ParseFloorsTests(unittest.TestCase):
    def test_accepts_boundaries(self):
        self.assertEqual(parse_floors({"apps": {"core": {"line": 0, "branch": 100}}}), {"core": (0.0, 100.0)})

    def test_rejects_missing_empty_or_malformed_apps(self):
        for config in ({}, {"apps": {}}, {"apps": []}):
            with self.subTest(config=config), self.assertRaises(ConfigurationError):
                parse_floors(config)

    def test_rejects_bad_app_names_and_floor_shapes(self):
        invalid = [
            {"apps": {"../core": {"line": 1, "branch": 1}}},
            {"apps": {"core": 90}},
            {"apps": {"core": {"line": 90}}},
            {"apps": {"core": {"line": 90, "branch": 90, "extra": 1}}},
        ]
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ConfigurationError):
                parse_floors(config)

    def test_rejects_non_numeric_non_finite_and_out_of_range_floors(self):
        for value in (True, "90", float("nan"), -0.01, 100.01):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                parse_floors({"apps": {"core": {"line": value, "branch": 90}}})


class CheckCoverageTests(unittest.TestCase):
    def test_line_and_branch_floors_are_independent_and_inclusive(self):
        floors = {"projects": (80, 75)}
        self.assertEqual(check_coverage(report(), floors), [])
        self.assertIn("line 80.00% is below 81.00%", check_coverage(report(), {"projects": (81, 0)})[0])
        self.assertIn("branch 75.00% is below 76.00%", check_coverage(report(), {"projects": (0, 76)})[0])

    def test_aggregates_multiple_files(self):
        data = report(lines=(4, 5), branches=(1, 2))
        data["files"]["src/apps/projects/two.py"] = report(lines=(5, 5), branches=(2, 2))["files"][
            "src/apps/projects/one.py"
        ]
        self.assertEqual(check_coverage(data, {"projects": (90, 75)}), [])

    def test_accepts_coverage_omitting_counts_for_files_without_branches(self):
        for branch_counts in ({}, {"covered_branches": None, "num_branches": None}):
            with self.subTest(branch_counts=branch_counts):
                data = report()
                data["files"]["src/apps/projects/no_branches.py"] = {
                    "summary": {
                        "covered_lines": 2,
                        "num_statements": 2,
                        **branch_counts,
                    }
                }
                self.assertEqual(check_coverage(data, {"projects": (80, 75)}), [])

    def test_rejects_inconsistent_missing_branch_counts(self):
        for branch_counts in (
            {"covered_branches": 0},
            {"num_branches": 0},
            {"covered_branches": None, "num_branches": 0},
            {"covered_branches": 0, "num_branches": None},
        ):
            with self.subTest(branch_counts=branch_counts):
                data = report()
                data["files"]["src/apps/projects/no_branches.py"] = {
                    "summary": {
                        "covered_lines": 2,
                        "num_statements": 2,
                        **branch_counts,
                    }
                }
                with self.assertRaisesRegex(ConfigurationError, "inconsistent branch counts"):
                    check_coverage(data, {"projects": (80, 75)})

    def test_does_not_match_app_name_prefix(self):
        self.assertIn("no coverage files found", check_coverage(report(app="projects_extra"), {"projects": (0, 0)})[0])

    def test_reports_missing_app_and_zero_denominators(self):
        self.assertIn(
            "no coverage files found",
            check_coverage({"meta": {"branch_coverage": True}, "files": {}}, {"core": (90, 90)})[0],
        )
        failures = check_coverage(report(lines=(0, 0), branches=(0, 0)), {"projects": (0, 0)})
        self.assertEqual(len(failures), 2)
        self.assertIn("no executable lines", failures[0])
        self.assertIn("zero branches", failures[1])

    def test_rejects_report_without_branch_collection(self):
        for meta in ({}, {"branch_coverage": False}, None):
            with self.subTest(meta=meta):
                data = report()
                if meta is None:
                    data.pop("meta")
                else:
                    data["meta"] = meta
                with self.assertRaisesRegex(ConfigurationError, "branch coverage enabled"):
                    check_coverage(data, {"projects": (0, 0)})

    def test_rejects_malformed_report_and_counts(self):
        invalid = [{}, {"files": []}, {"files": {"src/apps/core/a.py": {}}}]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ConfigurationError):
                check_coverage(data, {"core": (0, 0)})
        for value in (-1, 1.5, True, None):
            data = report()
            data["files"]["src/apps/projects/one.py"]["summary"]["covered_lines"] = value
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                check_coverage(data, {"projects": (0, 0)})


class MainTests(unittest.TestCase):
    def run_main(self, coverage, floors, *args):
        with tempfile.TemporaryDirectory() as directory:
            coverage_path = Path(directory) / "coverage.json"
            floors_path = Path(directory) / "floors.json"
            coverage_path.write_text(json.dumps(coverage), encoding="utf-8")
            floors_path.write_text(json.dumps(floors), encoding="utf-8")
            stdout, stderr = StringIO(), StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main([str(coverage_path), str(floors_path), *args])
            return code, stdout.getvalue(), stderr.getvalue()

    def test_success(self):
        code, stdout, stderr = self.run_main(report(), {"apps": {"projects": {"line": 80, "branch": 75}}})
        self.assertEqual(code, 0)
        self.assertIn("passed for 1 app", stdout)
        self.assertEqual(stderr, "")

    def test_floor_failure(self):
        code, _, stderr = self.run_main(report(), {"apps": {"projects": {"line": 100, "branch": 100}}})
        self.assertEqual(code, 1)
        self.assertIn("line 80.00%", stderr)
        self.assertIn("branch 75.00%", stderr)

    def test_selects_one_matrix_app(self):
        code, stdout, stderr = self.run_main(
            report(),
            {"apps": {"projects": {"line": 80, "branch": 75}, "cms": {"line": 100, "branch": 100}}},
            "--app",
            "projects",
        )
        self.assertEqual(code, 0)
        self.assertIn("passed for 1 app", stdout)
        self.assertEqual(stderr, "")

    def test_rejects_unknown_selected_app(self):
        code, _, stderr = self.run_main(report(), {"apps": {"projects": {"line": 80, "branch": 75}}}, "--app", "cms")
        self.assertEqual(code, 2)
        self.assertIn("is not configured", stderr)

    def test_malformed_json_and_missing_file_return_configuration_error(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.json"
            bad.write_text("not json", encoding="utf-8")
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = main([str(bad), str(Path(directory) / "missing.json")])
            self.assertEqual(code, 2)
            self.assertIn("cannot read coverage file", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
