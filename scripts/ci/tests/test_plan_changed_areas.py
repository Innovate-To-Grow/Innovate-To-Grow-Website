from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.ci.plan_changed_areas import FULL_SUITE, NO_SUITE, ChangedAreasPlan, plan_changed_areas

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PLANNER = REPOSITORY_ROOT / "scripts" / "ci" / "plan_changed_areas.py"


class PlanChangedAreasTests(unittest.TestCase):
    def test_non_pr_event_runs_all_areas(self) -> None:
        for event_name in ("push", "workflow_dispatch", "schedule"):
            with self.subTest(event_name=event_name):
                plan = plan_changed_areas(event_name, ["docs/architecture.md"])
                self.assertEqual(plan, ChangedAreasPlan(backend=True, frontend=True, cli=True, archive=True))

    def test_pull_request_touching_any_ci_area_runs_the_full_suite(self) -> None:
        for changed_file in (
            "src/apps/authn/models.py",
            "pages/src/App.tsx",
            "cli/src/i2g_admin/app.py",
            "archive/page/app.py",
            "aws/task-definition.json",
            "scripts/ci/validate_tool_versions.py",
            ".github/workflows/ci.yml",
            "pyproject.toml",
            ".pre-commit-config.yaml",
            ".bandit-baseline.json",
        ):
            with self.subTest(changed_file=changed_file):
                self.assertEqual(plan_changed_areas("pull_request", [changed_file]), FULL_SUITE)

    def test_pr_only_paths_run_nothing(self) -> None:
        for changed_file in (".claude/settings.json", "docs/architecture.md", "README.md", "uv.lock"):
            with self.subTest(changed_file=changed_file):
                self.assertEqual(plan_changed_areas("pull_request", [changed_file]), NO_SUITE)

    def test_pull_request_and_push_agree_whenever_ci_runs(self) -> None:
        # The parity invariant: if merging this diff would start a CI run, the PR
        # must have run the same job set. Regression guard for the green-PR /
        # red-main class of failure (run 32107167026).
        for changed_files in (
            ["src/apps/authn/views/account/profile.py"],
            ["pages/src/App.tsx"],
            ["archive/page/app.py"],
            ["cli/pyproject.toml"],
        ):
            with self.subTest(changed_files=changed_files):
                self.assertEqual(
                    plan_changed_areas("pull_request", changed_files),
                    plan_changed_areas("push", changed_files),
                )

    def test_github_change_runs_all_four_areas(self) -> None:
        plan = plan_changed_areas("pull_request", [".github/workflows/ci.yml"])

        self.assertEqual(plan, ChangedAreasPlan(backend=True, frontend=True, cli=True, archive=True))

    def test_multiple_areas_are_combined(self) -> None:
        plan = plan_changed_areas(
            "pull_request",
            ["src/apps/authn/models.py", "pages/src/App.tsx", "cli/pyproject.toml", "archive/page/app.py"],
        )

        self.assertEqual(plan, ChangedAreasPlan(backend=True, frontend=True, cli=True, archive=True))

    def test_empty_and_whitespace_paths_are_ignored(self) -> None:
        plan = plan_changed_areas("pull_request", ["", "  ", "\n"])

        self.assertEqual(plan, ChangedAreasPlan(backend=False, frontend=False, cli=False, archive=False))

    def test_near_miss_paths_do_not_match(self) -> None:
        plan = plan_changed_areas(
            "pull_request",
            ["src-notes/file.md", "pages.md", "archive.txt", "github/workflows/ci.yml"],
        )

        self.assertEqual(plan, ChangedAreasPlan(backend=False, frontend=False, cli=False, archive=False))

    def test_github_outputs_use_lowercase_booleans(self) -> None:
        outputs = ChangedAreasPlan(backend=True, frontend=False, cli=True, archive=True).github_outputs()

        self.assertEqual(outputs, "backend=true\nfrontend=false\ncli=true\narchive=true")

    def test_cli_reads_40000_paths_without_pipe_or_argument_limits(self) -> None:
        paths = [f"docs/generated/{index}.md" for index in range(39_997)]
        paths.extend(["src/apps/authn/models.py", "pages/src/App.tsx", "cli/pyproject.toml", "archive/page/app.py"])
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as changed_files:
            changed_files.write("\n".join(paths))
            changed_files.flush()

            result = subprocess.run(
                [
                    sys.executable,
                    str(PLANNER),
                    "--event-name",
                    "pull_request",
                    "--changed-files",
                    changed_files.name,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.stdout.strip(), "backend=true\nfrontend=true\ncli=true\narchive=true")


if __name__ == "__main__":
    unittest.main()
