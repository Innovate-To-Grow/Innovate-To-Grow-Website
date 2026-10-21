from __future__ import annotations

import ast
import textwrap
import unittest

from scripts.ci.check_python_quality import (
    Config,
    Finding,
    Profile,
    analyze_source,
    code_lines,
    directory_findings,
    evaluate,
    load_config,
    max_nesting,
)

STRICT = Profile(name="strict", file_lines=(2, 4), function_lines=(2, 4), nesting=(1, 2))


def _config(**overrides) -> Config:
    values = {
        "roots": ["src"],
        "exclude": ["*/migrations/*"],
        "profiles": [Profile(name="tests", patterns=["*/tests/*"]), STRICT],
        "directory_files": (2, 3),
        "exceptions": {},
    }
    values.update(overrides)
    return Config(**values)


def _function(source: str) -> ast.AST:
    return ast.parse(textwrap.dedent(source)).body[0]


class CodeLineCountingTests(unittest.TestCase):
    def test_blank_comment_and_docstring_lines_are_not_counted(self) -> None:
        source = textwrap.dedent(
            '''\
            """Module docstring
            spanning two lines."""

            # a comment
            def f():
                """Function docstring."""

                return 1  # trailing comments keep their line
            '''
        )
        self.assertEqual(sorted(code_lines(source, ast.parse(source))), [5, 8])

    def test_a_multi_line_statement_counts_every_physical_line(self) -> None:
        source = "value = [\n    1,\n    2,\n]\n"
        self.assertEqual(len(code_lines(source, ast.parse(source))), 4)


class NestingTests(unittest.TestCase):
    def test_elif_chains_count_as_one_level(self) -> None:
        function = _function(
            """\
            def f(x):
                if x == 1:
                    pass
                elif x == 2:
                    pass
                elif x == 3:
                    if x:
                        pass
            """
        )
        self.assertEqual(max_nesting(function), 2)

    def test_nested_functions_are_measured_on_their_own(self) -> None:
        function = _function(
            """\
            def outer():
                for item in items:
                    def inner():
                        if item:
                            if item:
                                pass
            """
        )
        self.assertEqual(max_nesting(function), 1)


class AnalyzeSourceTests(unittest.TestCase):
    def test_reports_advisory_and_hard_findings_per_metric(self) -> None:
        source = textwrap.dedent(
            """\
            def long(x):
                a = 1
                b = 2
                c = 3
                for i in x:
                    if i:
                        while i:
                            i -= 1
            """
        )
        findings = {finding.metric: finding for finding in analyze_source("src/a.py", source, STRICT)}
        self.assertTrue(findings["file-lines"].is_hard)
        self.assertEqual(findings["function-lines"].symbol, "long")
        self.assertEqual(findings["nesting"].value, 3)
        self.assertTrue(findings["nesting"].is_hard)

    def test_disabled_metrics_produce_nothing(self) -> None:
        source = "def f():\n" + "    x = 1\n" * 50
        self.assertEqual(analyze_source("src/tests/test_a.py", source, Profile(name="off")), [])

    def test_methods_are_named_by_their_class(self) -> None:
        source = "class A:\n    def m(self):\n        a = 1\n        b = 2\n        return a + b\n"
        symbols = {finding.symbol for finding in analyze_source("src/a.py", source, STRICT)}
        self.assertIn("A.m", symbols)


class ConfigTests(unittest.TestCase):
    def test_first_matching_profile_wins_and_the_last_is_the_default(self) -> None:
        config = _config()
        self.assertEqual(config.profile_for("src/apps/x/tests/test_a.py").name, "tests")
        self.assertEqual(config.profile_for("src/apps/x/models.py").name, "strict")

    def test_star_crosses_directories(self) -> None:
        self.assertTrue(_config().is_excluded("src/apps/x/migrations/0001_initial.py"))

    def test_repository_config_loads_and_ends_with_a_catch_all_profile(self) -> None:
        config = load_config()
        self.assertEqual(config.profiles[-1].patterns, ["*"])
        for key, reason in config.exceptions.items():
            with self.subTest(key=key):
                self.assertTrue(reason.strip(), "every exception needs a reason")


class DirectoryAndEvaluationTests(unittest.TestCase):
    def test_package_markers_do_not_count_toward_directory_size(self) -> None:
        files = ["src/p/__init__.py", "src/p/a.py", "src/p/b.py", "src/p/c.py", "src/q/a.py"]
        (finding,) = directory_findings(files, _config())
        self.assertEqual((finding.path, finding.value, finding.is_hard), ("src/p", 3, False))

    def test_excepted_hard_findings_pass_and_stale_exceptions_are_reported(self) -> None:
        hard = Finding("nesting", "src/a.py", "f", 9, 3, 4)
        advisory = Finding("nesting", "src/b.py", "g", 4, 3, 4)
        config = _config(exceptions={hard.key: "why", "nesting:src/gone.py::h": "fixed already"})
        unexcused, stale = evaluate([hard, advisory], config)
        self.assertEqual(unexcused, [])
        self.assertEqual(stale, ["nesting:src/gone.py::h"])

    def test_unexcused_hard_findings_fail(self) -> None:
        hard = Finding("file-lines", "src/a.py", "", 900, 300, 500)
        self.assertEqual(evaluate([hard], _config()), ([hard], []))
        self.assertEqual(hard.key, "file-lines:src/a.py")


if __name__ == "__main__":
    unittest.main()
