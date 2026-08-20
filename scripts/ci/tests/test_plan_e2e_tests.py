import json
import re
import unittest
from pathlib import Path

from scripts.ci.plan_e2e_tests import FULL_PROJECTS, plan_e2e_tests

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class PlanE2ETests(unittest.TestCase):
    def test_full_matrix_includes_current_flagship_devices(self):
        plan = plan_e2e_tests("push", ["pages/src/features/auth/components/Login.tsx"])

        for device in ("iphone-17-pro-max", "galaxy-s26-ultra", "galaxy-tab-s9"):
            self.assertIn(device, plan.projects)

    def test_every_event_runs_the_full_project_matrix(self):
        # PR/push parity: a device-specific failure must not be able to hide
        # until after the merge (run 32107167026, iphone14 + ipad).
        for event_name in ("push", "pull_request", "workflow_dispatch"):
            for changed_files in (
                [],
                ["pages/src/features/auth/components/Login.tsx"],
                ["src/apps/authn/models.py"],
                ["pages/e2e/mobile.spec.ts"],
            ):
                with self.subTest(event_name=event_name, changed_files=changed_files):
                    plan = plan_e2e_tests(event_name, changed_files)
                    self.assertEqual(plan.projects, FULL_PROJECTS)
                    self.assertEqual(plan.specs, [])
                    self.assertTrue(all(leg.spec_args == "" for leg in plan.matrix))

    def test_full_projects_match_playwright_config(self):
        # FULL_PROJECTS is the single source of the CI device matrix; drift from
        # pages/playwright.config.ts silently drops or invents a leg.
        config = (REPOSITORY_ROOT / "pages" / "playwright.config.ts").read_text(encoding="utf-8")
        declared = re.findall(r"\{name: '([^']+)'", config)

        self.assertEqual(sorted(declared), sorted(FULL_PROJECTS))

    def test_github_outputs_include_full_matrix_json(self):
        plan = plan_e2e_tests("pull_request", ["pages/src/features/projects/api/client.ts"])
        outputs = dict(line.split("=", 1) for line in plan.github_outputs().splitlines())

        self.assertEqual(json.loads(outputs["projects"]), FULL_PROJECTS)
        self.assertEqual(json.loads(outputs["specs"]), [])
        self.assertEqual(outputs["spec_args"], "")
        self.assertEqual(
            json.loads(outputs["matrix"]),
            [{"project": project, "spec_args": ""} for project in FULL_PROJECTS],
        )


if __name__ == "__main__":
    unittest.main()
