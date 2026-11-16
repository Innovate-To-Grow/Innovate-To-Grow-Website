from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts.structure.checker.config import CONFIG_PATH, RULES, ConfigError, glob_match, load_config

MINIMAL = """
[limits]
file_lines = 200
directory_files = 8
directory_subdirs = 8
module_depth = 6

[measure]
source_extensions = [".py"]
entry_files = ["**/__init__.py"]

[migrations]
protected = ["**/migrations/**"]
"""


def load_text(text: str):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "structure.toml"
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return load_config(path)


class GlobTests(unittest.TestCase):
    def test_single_star_stays_inside_one_segment(self) -> None:
        self.assertTrue(glob_match("src/apps/*", "src/apps/core"))
        self.assertFalse(glob_match("src/apps/*", "src/apps/core/models"))
        self.assertTrue(glob_match("src/apps/*/management/commands", "src/apps/mail/management/commands"))

    def test_double_star_spans_any_depth_including_none(self) -> None:
        self.assertTrue(glob_match("**/migrations/**", "src/apps/core/migrations/0001_initial.py"))
        self.assertTrue(glob_match("**/migrations/**", "migrations/__init__.py"))
        self.assertTrue(glob_match("**/migrations/**", "src/apps/event/tests/migrations/test_x.py"))
        self.assertFalse(glob_match("**/migrations/**", "src/apps/core/migration_helpers.py"))
        self.assertTrue(glob_match("pages/public/**", "pages/public/assets/images/logo.png"))
        self.assertFalse(glob_match("pages/public/**", "pages/public"))

    def test_root_and_literal_characters(self) -> None:
        self.assertTrue(glob_match(".", "."))
        self.assertFalse(glob_match(".", "a"))
        self.assertTrue(glob_match("a+b/[x].py", "a+b/[x].py"))
        self.assertTrue(glob_match("file?.py", "file1.py"))
        self.assertFalse(glob_match("file?.py", "file/.py"))


class LoadConfigTests(unittest.TestCase):
    def test_the_repository_config_is_valid(self) -> None:
        config = load_config(CONFIG_PATH)
        self.assertEqual(config.limits.file_lines, 200)
        self.assertEqual(config.limits.directory_files, 8)
        self.assertEqual(config.limits.directory_subdirs, 8)
        self.assertIn("**/migrations/**", config.protected_migrations)
        self.assertEqual(config.allowed_migration_changes, ())
        for entry in (*config.unmeasured, *config.exceptions):
            with self.subTest(entry=entry.label):
                self.assertTrue(entry.reason)
                self.assertTrue(set(entry.rules) <= set(RULES))

    def test_the_repository_config_never_unmeasures_whole_source_trees(self) -> None:
        config = load_config(CONFIG_PATH)
        for entry in config.unmeasured:
            for pattern in entry.patterns:
                with self.subTest(pattern=pattern):
                    self.assertNotIn(pattern, {"**", "src/**", "pages/**", "pages/src/**", "src/apps/**"})

    def test_minimal_config_defaults(self) -> None:
        config = load_text(MINIMAL)
        self.assertEqual(config.exceptions, ())
        self.assertEqual(config.unmeasured, ())
        self.assertTrue(config.measure.is_source("a/b.py"))
        self.assertFalse(config.measure.is_source("a/b.md"))
        self.assertTrue(config.measure.is_entry_file("pkg/__init__.py"))

    def test_an_exception_needs_a_reason_and_known_rules(self) -> None:
        for body in (
            '[[exceptions]]\npaths = ["x"]\nrules = ["R001"]\n',
            '[[exceptions]]\npaths = ["x"]\nreason = "r"\n',
            '[[exceptions]]\npaths = ["x"]\nrules = ["R999"]\nreason = "r"\n',
            '[[exceptions]]\npaths = []\nrules = ["R001"]\nreason = "r"\n',
        ):
            with self.subTest(body=body), self.assertRaises(ConfigError):
                load_text(MINIMAL + body)

    def test_limits_must_be_complete_positive_integers(self) -> None:
        for broken in (MINIMAL.replace("module_depth = 6", ""), MINIMAL.replace("= 200", "= 0")):
            with self.subTest(), self.assertRaises(ConfigError):
                load_text(broken)
        with self.assertRaises(ConfigError):
            load_text(MINIMAL.replace("module_depth = 6", "module_depth = 6\nunknown = 1"))

    def test_unreadable_or_invalid_toml_is_a_config_error(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(Path("/nonexistent/structure.toml"))
        with self.assertRaises(ConfigError):
            load_text("[limits\n")
        with self.assertRaises(ConfigError):
            load_text("[measure]\nsource_extensions = []\n")


if __name__ == "__main__":
    unittest.main()
