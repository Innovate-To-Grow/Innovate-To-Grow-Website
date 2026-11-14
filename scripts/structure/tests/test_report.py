from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from scripts.structure.checker.__main__ import main
from scripts.structure.checker.config import Entry
from scripts.structure.checker.report import counts, render_json, render_markdown, render_text
from scripts.structure.checker.rules import Finding, Outcome
from scripts.structure.tests.fixtures import GitRepository, make_config

CONFIG = """
[limits]
file_lines = 3
directory_files = 2
directory_subdirs = 2
module_depth = 6

[measure]
source_extensions = [".py"]
entry_files = ["**/__init__.py"]

[[exceptions]]
paths = ["big.py"]
rules = ["R001"]
reason = "kept on purpose"

[[exceptions]]
paths = ["."]
rules = ["R003-mixed"]
reason = "test repository root"

[migrations]
protected = ["**/migrations/**"]
"""


def sample_outcome() -> Outcome:
    entry = Entry(("big.py",), "kept on purpose", ("R001",))
    return Outcome(
        active=[Finding("R002", "pkg", 3, 2), Finding("R004-depth", "a/b/c.py", 7, 6)],
        excepted={entry: [Finding("R001", "big.py", 9, 3)]},
        stale_exceptions=[Entry(("gone.py",), "old", ("R001",))],
    )


class RenderTests(unittest.TestCase):
    def test_counts_cover_every_rule(self) -> None:
        self.assertEqual(counts(sample_outcome())["R001"], (0, 1))
        self.assertEqual(counts(sample_outcome())["R002"], (1, 0))
        self.assertEqual(counts(sample_outcome())["R003-width"], (0, 0))

    def test_text_lists_findings_only_when_verbose(self) -> None:
        config = make_config()
        quiet = render_text(sample_outcome(), config, "report", verbose=False)
        loud = render_text(sample_outcome(), config, "report", verbose=True)
        self.assertNotIn("pkg  3 files", quiet)
        self.assertIn("R002       pkg  3 files (limit 2)", loud)
        self.assertIn("stale exception (matches nothing): gone.py [R001]", quiet)
        self.assertIn("Report-only", quiet)

    def test_markdown_has_a_summary_table_and_collapsed_lists(self) -> None:
        markdown = render_markdown(sample_outcome(), make_config(), "report")
        self.assertIn("| R002 | 1 | 0 | Directories with more than 2 files |", markdown)
        self.assertIn("<details><summary>Directories with more than 2 files: 1</summary>", markdown)
        self.assertIn("- stale exception (matches nothing): gone.py [R001]", markdown)

    def test_json_is_machine_readable(self) -> None:
        data = json.loads(render_json(sample_outcome()))
        self.assertEqual(data["active"][0], {"rule": "R002", "path": "pkg", "value": 3, "limit": 2})
        self.assertEqual(data["excepted"][0]["reason"], "kept on purpose")
        self.assertEqual(data["stale_exceptions"], ["gone.py [R001]"])


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = GitRepository()
        self.addCleanup(self.repo.close)
        self.repo.commit(
            {"big.py": "1\n" * 9, "pkg/a.py": "", "pkg/b.py": "", "pkg/c.py": "", "structure.toml": CONFIG}
        )
        self.config = str(self.repo.root / "structure.toml")

    def run_main(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(["--root", str(self.repo.root), "--config", self.config, *args])
        return code, output.getvalue()

    def test_report_mode_never_fails_on_findings(self) -> None:
        code, output = self.run_main("report")
        self.assertEqual(code, 0)
        self.assertRegex(output, r"R002\s+1 open,\s+0 excepted")
        self.assertRegex(output, r"R001\s+0 open,\s+1 excepted")

    def test_enforce_mode_fails_on_open_findings(self) -> None:
        code, _ = self.run_main("report", "--mode", "enforce")
        self.assertEqual(code, 1)
        self.repo.commit(remove=("pkg/c.py",))
        code, _ = self.run_main("report", "--mode", "enforce")
        self.assertEqual(code, 0)

    def test_markdown_and_json_outputs(self) -> None:
        markdown, report = self.repo.root / "summary.md", self.repo.root / "out.json"
        markdown.write_text("previous step\n", encoding="utf-8")
        self.run_main("report", "--markdown", str(markdown), "--json", str(report))
        self.assertTrue(markdown.read_text(encoding="utf-8").startswith("previous step\n## Repository structure"))
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["active"][0]["path"], "pkg")

    def test_a_broken_config_exits_2(self) -> None:
        Path(self.config).write_text("[limits]\n", encoding="utf-8")
        code, output = self.run_main("report")
        self.assertEqual(code, 2)
        self.assertIn("ERROR:", output)


if __name__ == "__main__":
    unittest.main()
