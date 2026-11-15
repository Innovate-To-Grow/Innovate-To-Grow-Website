from __future__ import annotations

import contextlib
import io
import unittest
from dataclasses import replace

from scripts.structure.checker.__main__ import main
from scripts.structure.checker.config import Entry
from scripts.structure.checker.migrations import (
    ZERO_SHA,
    Change,
    changed_paths,
    parse_name_status,
    protected_changes,
    resolve_base,
    run_guard,
)
from scripts.structure.tests.fixtures import GitRepository, make_config

INITIAL = "src/apps/core/migrations/0001_initial.py"
TEST_MODULE = "src/apps/core/tests/migrations/test_0001.py"


class ParseTests(unittest.TestCase):
    def test_renames_and_copies_carry_two_paths(self) -> None:
        output = "M\0a.py\0R087\0old.py\0new.py\0D\0gone.py\0C100\0src.py\0copy.py\0A\0new2.py\0"
        self.assertEqual(
            parse_name_status(output),
            [
                Change("M", "a.py"),
                Change("R087", "old.py", "new.py"),
                Change("D", "gone.py"),
                Change("C100", "src.py", "copy.py"),
                Change("A", "new2.py"),
            ],
        )

    def test_only_existing_protected_files_count(self) -> None:
        changes = [
            Change("A", "src/apps/core/migrations/0002_new.py"),
            Change("C100", INITIAL, "src/apps/core/migrations/0003_copy.py"),
            Change("M", "src/apps/core/models.py"),
            Change("M", INITIAL),
            Change("R100", "src/apps/mail/migrations/0004_x.py", "src/apps/mail/old/0004_x.py"),
        ]
        problems = protected_changes(changes, make_config())
        self.assertEqual([change.path for change in problems], [INITIAL, "src/apps/mail/migrations/0004_x.py"])
        self.assertIn("was renamed to src/apps/mail/old/0004_x.py", problems[1].describe())

    def test_an_explicitly_allowed_change_passes(self) -> None:
        allowed = (Entry((INITIAL,), "approved by the owners"),)
        config = replace(make_config(), allowed_migration_changes=allowed)
        self.assertEqual(protected_changes([Change("M", INITIAL)], config), [])


class GuardRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = GitRepository()
        self.addCleanup(self.repo.close)
        self.base = self.repo.commit({INITIAL: "initial\n", TEST_MODULE: "test\n", "src/apps/core/models.py": "m\n"})

    def guard(self, base: str, head: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run_guard(self.repo.root, base, head, make_config())
        return code, output.getvalue()

    def test_adding_a_migration_and_editing_other_code_pass(self) -> None:
        head = self.repo.commit({"src/apps/core/migrations/0002_more.py": "new\n", "src/apps/core/models.py": "m2\n"})
        code, output = self.guard(self.base, head)
        self.assertEqual(code, 0)
        self.assertIn("1 protected file(s) added", output)

    def test_editing_deleting_or_renaming_an_existing_migration_fails(self) -> None:
        for change in ({"files": {INITIAL: "edited\n"}}, {"remove": (INITIAL,)}, {"files": {TEST_MODULE: "x\n"}}):
            with self.subTest(change=change):
                self.repo.git("checkout", "-q", "-B", "case", self.base)
                head = self.repo.commit(**change)
                code, output = self.guard(self.base, head)
                self.assertEqual(code, 1)
                self.assertIn("ERROR:", output)
        self.repo.git("checkout", "-q", "-b", "rename", self.base)
        self.repo.git("mv", INITIAL, "src/apps/core/migrations/0001_renamed.py")
        head = self.repo.commit()
        self.assertEqual(changed_paths(self.repo.root, self.base, head)[0].status[0], "R")
        self.assertEqual(self.guard(self.base, head)[0], 1)

    def test_the_diff_starts_at_the_merge_base(self) -> None:
        self.repo.git("checkout", "-q", "-b", "feature")
        feature = self.repo.commit({"src/apps/core/models.py": "feature\n"})
        self.repo.git("checkout", "-q", "main")
        main_head = self.repo.commit({INITIAL: "edited on main by someone else\n"})
        self.assertEqual(resolve_base(self.repo.root, main_head, feature), self.base)
        self.assertEqual(self.guard(main_head, feature)[0], 0)

    def test_an_unusable_base_falls_back_to_the_first_parent(self) -> None:
        head = self.repo.commit({INITIAL: "edited\n"})
        for base in ("", ZERO_SHA, "f" * 40):
            with self.subTest(base=base):
                self.assertEqual(resolve_base(self.repo.root, base, head), self.base)
                self.assertEqual(self.guard(base, head)[0], 1)

    def test_a_root_commit_has_nothing_to_compare(self) -> None:
        code, output = self.guard("", self.base)
        self.assertEqual(code, 0)
        self.assertIn("nothing to compare", output)

    def test_the_command_line_reports_an_unknown_head_as_exit_2(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(["--root", str(self.repo.root), "migrations", "--base", self.base, "--head", "f" * 40])
        self.assertEqual(code, 2)
        self.assertIn("ERROR: git merge-base", output.getvalue())


if __name__ == "__main__":
    unittest.main()
