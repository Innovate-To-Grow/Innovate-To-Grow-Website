import json
import unittest

from scripts.ci.plan_django_tests import ALL_APPS, plan_django_tests


class PlanDjangoTests(unittest.TestCase):
    def test_main_push_runs_all_apps_and_cli_coverage(self):
        plan = plan_django_tests("push", ["src/apps/projects/models.py"])

        self.assertEqual(plan.apps, ALL_APPS)
        self.assertTrue(plan.cli_admin_coverage)

    def test_app_local_change_runs_only_that_app(self):
        plan = plan_django_tests("pull_request", ["src/apps/projects/views.py"])

        self.assertEqual(plan.apps, ["projects"])
        self.assertFalse(plan.cli_admin_coverage)

    def test_cli_admin_change_enables_cli_coverage(self):
        plan = plan_django_tests("pull_request", ["src/apps/cli_admin/management/commands/i2g.py"])

        self.assertEqual(plan.apps, ["cli_admin"])
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

        self.assertEqual(json.loads(outputs["apps"]), ["authn"])
        self.assertEqual(outputs["cli_admin_coverage"], "false")


if __name__ == "__main__":
    unittest.main()
