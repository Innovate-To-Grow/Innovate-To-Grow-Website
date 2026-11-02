import json
import unittest
from pathlib import Path

from scripts.ci.plan_django_tests import ALL_APPS, plan_django_tests

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class PlanDjangoTests(unittest.TestCase):
    def test_every_event_runs_all_apps_and_cli_coverage(self):
        # PR/push parity: a cross-app regression or a drop below the 100% floor
        # on apps.cli_admin + safe_orm must not first surface on main.
        for event_name in ("push", "pull_request", "workflow_dispatch"):
            for changed_files in (
                [],
                ["src/apps/projects/views.py"],
                ["src/apps/cli_admin/management/commands/i2g.py"],
            ):
                with self.subTest(event_name=event_name, changed_files=changed_files):
                    plan = plan_django_tests(event_name, changed_files)
                    self.assertEqual(plan.apps, ALL_APPS)
                    self.assertTrue(plan.cli_admin_coverage)

    def test_shared_backend_change_runs_all(self):
        plan = plan_django_tests("pull_request", ["src/apps/core/services/db_tools/safe_orm.py"])

        self.assertEqual(plan.apps, ALL_APPS)
        self.assertTrue(plan.cli_admin_coverage)

    def test_workflow_change_runs_all(self):
        plan = plan_django_tests("pull_request", [".github/workflows/ci.yml"])

        self.assertEqual(plan.apps, ALL_APPS)
        self.assertTrue(plan.cli_admin_coverage)

    def test_github_outputs_are_compact_json(self):
        plan = plan_django_tests("pull_request", ["src/apps/authn/views/login.py"])
        outputs = dict(line.split("=", 1) for line in plan.github_outputs().splitlines())

        self.assertEqual(json.loads(outputs["apps"]), ALL_APPS)
        self.assertEqual(outputs["cli_admin_coverage"], "true")

    def test_every_django_app_has_a_matrix_leg_and_a_coverage_floor(self):
        # A new src/apps/<app>/ would otherwise get no Django test leg and no
        # coverage floor, and nothing else in CI would notice.
        apps_on_disk = sorted(path.parent.name for path in (REPOSITORY_ROOT / "src" / "apps").glob("*/apps.py"))
        floors_path = REPOSITORY_ROOT / "scripts" / "ci" / "backend_coverage_floors.json"
        floors = json.loads(floors_path.read_text(encoding="utf-8"))["apps"]

        self.assertEqual(sorted(ALL_APPS), apps_on_disk)
        self.assertEqual(sorted(floors), apps_on_disk)


if __name__ == "__main__":
    unittest.main()
