from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.ci.plan_changed_areas import ChangedAreasPlan, plan_changed_areas

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PLANNER = REPOSITORY_ROOT / "scripts" / "ci" / "plan_changed_areas.py"


class PlanChangedAreasTests(unittest.TestCase):
    def test_non_pr_event_runs_all_areas(self) -> None:
        for event_name in ("push", "workflow_dispatch", "schedule"):
            with self.subTest(event_name=event_name):
                plan = plan_changed_areas(event_name, ["docs/architecture.md"])
                self.assertEqual(plan, ChangedAreasPlan(backend=True, frontend=True, archive=True))

    def test_pull_request_scopes_each_area(self) -> None:
        cases = {
            "src/apps/authn/models.py": ChangedAreasPlan(True, False, False),
            "pages/src/App.tsx": ChangedAreasPlan(False, True, False),
            "archive/page/app.py": ChangedAreasPlan(False, False, True),
            "docs/architecture.md": ChangedAreasPlan(False, False, False),
        }
        for changed_file, expected in cases.items():
            with self.subTest(changed_file=changed_file):
                self.assertEqual(plan_changed_areas("pull_request", [changed_file]), expected)

    def test_backend_shared_paths_preserve_existing_semantics(self) -> None:
        changed_files = [
            "aws/task-definition.json",
            "scripts/ci/validate_tool_versions.py",
            "pyproject.toml",
            ".pre-commit-config.yaml",
            ".bandit-baseline.json",
        ]
        for changed_file in changed_files:
            with self.subTest(changed_file=changed_file):
                self.assertEqual(
                    plan_changed_areas("pull_request", [changed_file]),
                    ChangedAreasPlan(backend=True, frontend=False, archive=False),
                )

    def test_github_change_runs_backend_and_frontend_but_not_archive(self) -> None:
        plan = plan_changed_areas("pull_request", [".github/workflows/ci.yml"])

        self.assertEqual(plan, ChangedAreasPlan(backend=True, frontend=True, archive=False))

    def test_multiple_areas_are_combined(self) -> None:
        plan = plan_changed_areas(
            "pull_request",
            ["src/apps/authn/models.py", "pages/src/App.tsx", "archive/page/app.py"],
        )

        self.assertEqual(plan, ChangedAreasPlan(backend=True, frontend=True, archive=True))

    def test_empty_and_whitespace_paths_are_ignored(self) -> None:
        plan = plan_changed_areas("pull_request", ["", "  ", "\n"])

        self.assertEqual(plan, ChangedAreasPlan(backend=False, frontend=False, archive=False))

    def test_near_miss_paths_do_not_match(self) -> None:
        plan = plan_changed_areas(
            "pull_request",
            ["src-notes/file.md", "pages.md", "archive.txt", "github/workflows/ci.yml"],
        )

        self.assertEqual(plan, ChangedAreasPlan(backend=False, frontend=False, archive=False))

    def test_github_outputs_use_lowercase_booleans(self) -> None:
        outputs = ChangedAreasPlan(backend=True, frontend=False, archive=True).github_outputs()

        self.assertEqual(outputs, "backend=true\nfrontend=false\narchive=true")

    def test_cli_reads_40000_paths_without_pipe_or_argument_limits(self) -> None:
        paths = [f"docs/generated/{index}.md" for index in range(39_997)]
        paths.extend(["src/apps/authn/models.py", "pages/src/App.tsx", "archive/page/app.py"])
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

        self.assertEqual(result.stdout.strip(), "backend=true\nfrontend=true\narchive=true")


if __name__ == "__main__":
    unittest.main()
