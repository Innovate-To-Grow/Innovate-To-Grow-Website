from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.structure.checker.config import Entry
from scripts.structure.checker.rules import Finding, apply_exceptions, evaluate, module_root
from scripts.structure.checker.tree import build_tree, count_lines, index_directories
from scripts.structure.tests.fixtures import make_config, write


class TreeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def findings(self, files: dict[str, str], **overrides) -> list[Finding]:
        write(self.root, files)
        config = make_config(**overrides)
        return evaluate(build_tree(self.root, config, sorted(files)), config)

    def keys(self, files: dict[str, str], **overrides) -> set[tuple[str, str]]:
        return {(finding.rule, finding.path) for finding in self.findings(files, **overrides)}


class LineCountTests(TreeTestCase):
    def test_physical_lines_include_blank_lines_and_an_unterminated_last_line(self) -> None:
        write(self.root, {"a.py": "x = 1\n\n# c\n", "b.py": "x\ny", "c.py": ""})
        self.assertEqual([count_lines(self.root / name) for name in ("a.py", "b.py", "c.py")], [3, 2, 0])

    def test_only_source_files_over_the_limit_are_findings(self) -> None:
        found = self.keys(
            {"a.py": "1\n2\n3\n", "b.py": "1\n2\n3\n4\n", "notes.md": "1\n2\n3\n4\n", "Dockerfile": "1\n" * 4}
        )
        self.assertEqual(found & {("R001", "a.py"), ("R001", "b.py"), ("R001", "notes.md")}, {("R001", "b.py")})
        self.assertIn(("R001", "Dockerfile"), found)


class DirectoryRuleTests(TreeTestCase):
    def test_too_many_files_hidden_files_count(self) -> None:
        found = self.keys({"pkg/a.py": "", "pkg/b.py": "", "pkg/.hidden": ""})
        self.assertIn(("R002", "pkg"), found)

    def test_package_init_files_do_not_count(self) -> None:
        found = self.keys({"pkg/__init__.py": "", "pkg/a.py": "", "pkg/b.py": "", "pkg/sub/__init__.py": ""})
        self.assertNotIn(("R002", "pkg"), found)
        self.assertIn(("R003-mixed", "pkg"), found)
        self.assertNotIn(("R003-mixed", "pkg/sub"), found)

    def test_a_package_of_subpackages_is_not_mixed(self) -> None:
        found = self.keys({"pkg/__init__.py": "", "pkg/one/a.py": "", "pkg/two/b.py": ""})
        self.assertNotIn(("R003-mixed", "pkg"), found)

    def test_a_feature_entry_point_does_not_mix_its_feature_root(self) -> None:
        files = {"app/features/auth/index.ts": "", "app/features/auth/api/a.ts": "", "app/other/index.ts": ""}
        files["app/other/sub/b.ts"] = ""
        found = self.keys(files)
        self.assertNotIn(("R003-mixed", "app/features/auth"), found)
        self.assertIn(("R003-mixed", "app/other"), found)

    def test_too_many_subdirectories(self) -> None:
        found = self.keys({"top/a/x.py": "", "top/b/x.py": "", "top/c/x.py": ""})
        self.assertIn(("R003-width", "top"), found)

    def test_dumping_ground_directory_names(self) -> None:
        found = self.keys({"tests/misc/test_a.py": "", "tests/miscellany/test_b.py": ""})
        self.assertIn(("R004-name", "tests/misc"), found)
        self.assertNotIn(("R004-name", "tests/miscellany"), found)

    def test_unmeasured_paths_are_invisible(self) -> None:
        files = {"vendor/a.py": "1\n" * 9, "vendor/b.py": "", "vendor/c.py": "", "vendor/x/d.py": ""}
        self.assertEqual(self.findings(files), [])

    def test_the_directory_index_records_the_root_as_dot(self) -> None:
        directories = index_directories(["a.py", "pkg/b.py"])
        self.assertEqual(directories["."].files, ["a.py"])
        self.assertEqual(directories["."].subdirs, {"pkg"})


class DepthRuleTests(TreeTestCase):
    def test_depth_is_measured_from_the_deepest_module_root(self) -> None:
        self.assertEqual(module_root("app/features/auth/api/x.ts", ("app/*", "app/features/*")), "app/features/auth")
        self.assertIsNone(module_root("lib/x.ts", ("app/features/*",)))
        files = {"app/features/auth/a/b.ts": "", "app/features/auth/a/b/c.ts": ""}
        depths = [finding for finding in self.findings(files) if finding.rule == "R004-depth"]
        self.assertEqual([(finding.path, finding.value) for finding in depths], [("app/features/auth/a/b/c.ts", 3)])
        self.assertTrue(depths[0].advisory)


class ExceptionTests(TreeTestCase):
    FILES = {"pkg/a.py": "1\n" * 5, "pkg/b.py": "", "pkg/c.py": "", "pkg/sub/d.py": ""}

    def outcome(self, *exceptions: Entry):
        write(self.root, self.FILES)
        config = make_config(exceptions=exceptions)
        tree = build_tree(self.root, config, sorted(self.FILES))
        return apply_exceptions(evaluate(tree, config), tree, config)

    def test_an_exception_covers_only_its_rules_and_paths(self) -> None:
        entry = Entry(("pkg",), "fixed by a framework", ("R002",))
        outcome = self.outcome(entry)
        self.assertEqual([(f.rule, f.path) for f in outcome.excepted[entry]], [("R002", "pkg")])
        self.assertIn(("R003-mixed", "pkg"), {(f.rule, f.path) for f in outcome.active})
        self.assertEqual(outcome.stale_exceptions, [])

    def test_stale_entries_fail_enforce_mode(self) -> None:
        stale = Entry(("nowhere",), "gone", ("R001",))
        outcome = self.outcome(stale)
        self.assertEqual(outcome.stale_exceptions, [stale])
        self.assertEqual(outcome.stale_unmeasured, list(make_config().unmeasured))
        self.assertTrue(outcome.failing)

    def test_only_advisory_findings_do_not_fail(self) -> None:
        outcome = self.outcome()
        outcome.active = [Finding("R004-depth", "x", 9, 6)]
        outcome.stale_unmeasured = []
        self.assertFalse(outcome.failing)


if __name__ == "__main__":
    unittest.main()
