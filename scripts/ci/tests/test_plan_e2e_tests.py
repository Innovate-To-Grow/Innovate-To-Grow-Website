import json
import unittest

from scripts.ci.plan_e2e_tests import FULL_PROJECTS, plan_e2e_tests


class PlanE2ETests(unittest.TestCase):
    def test_main_push_runs_full_project_matrix(self):
        plan = plan_e2e_tests("push", ["pages/src/features/auth/components/Login.tsx"])

        self.assertEqual(plan.projects, FULL_PROJECTS)
        self.assertEqual(plan.specs, [])
        self.assertTrue(all(leg.spec_args == "" for leg in plan.matrix))

    def test_full_matrix_includes_android_tablet_and_landscape_devices(self):
        plan = plan_e2e_tests("push", ["pages/src/features/auth/components/Login.tsx"])

        for device in ("galaxy-tab-s4", "pixel7-landscape", "iphone14-landscape"):
            self.assertIn(device, plan.projects)

    def test_auth_paths_run_auth_account_subscribe_profile_specs(self):
        plan = plan_e2e_tests("pull_request", ["pages/src/features/auth/components/Login.tsx"])

        self.assertEqual(plan.projects, ["chromium"])
        self.assertIn("e2e/auth-login.spec.ts", plan.specs)
        self.assertIn("e2e/account.spec.ts", plan.specs)
        self.assertIn("e2e/subscribe.spec.ts", plan.specs)
        self.assertIn("e2e/complete-profile.spec.ts", plan.specs)
        self.assertIn("e2e/cross-root-sync.spec.ts", plan.specs)

    def test_project_paths_run_projects_spec(self):
        plan = plan_e2e_tests("pull_request", ["pages/src/features/projects/api/client.ts"])

        self.assertEqual(plan.specs, ["e2e/projects.spec.ts"])
        self.assertEqual(plan.matrix[0].spec_args, "e2e/projects.spec.ts")

    def test_cms_news_content_layout_paths_run_content_specs(self):
        plan = plan_e2e_tests("pull_request", ["pages/src/features/cms/components/RichText.tsx"])

        self.assertIn("e2e/content-archive.spec.ts", plan.specs)
        self.assertIn("e2e/news.spec.ts", plan.specs)
        self.assertIn("e2e/smoke.live.spec.ts", plan.specs)
        self.assertIn("e2e/cross-root-sync.spec.ts", plan.specs)

    def test_event_paths_run_event_registration_spec(self):
        plan = plan_e2e_tests("pull_request", ["pages/src/routes/EventRegistrationPage/index.tsx"])

        self.assertEqual(plan.specs, ["e2e/event-registration.spec.ts"])

    def test_mobile_paths_add_pixel7_and_mobile_spec(self):
        plan = plan_e2e_tests("pull_request", ["pages/src/components/MobileMenu.tsx"])

        self.assertEqual(plan.projects, ["chromium", "pixel7"])
        self.assertIn("e2e/mobile.spec.ts", plan.specs)
        by_project = {leg.project: leg.spec_args for leg in plan.matrix}
        self.assertEqual(by_project["chromium"], "e2e/smoke.live.spec.ts")
        self.assertIn("e2e/mobile.spec.ts", by_project["pixel7"])

    def test_global_config_change_runs_full_chromium(self):
        plan = plan_e2e_tests("pull_request", ["pages/playwright.config.ts"])

        self.assertEqual(plan.projects, ["chromium"])
        self.assertEqual(plan.specs, [])
        self.assertEqual(plan.matrix[0].spec_args, "")

    def test_github_outputs_include_matrix_json(self):
        plan = plan_e2e_tests("pull_request", ["pages/src/features/projects/api/client.ts"])
        outputs = dict(line.split("=", 1) for line in plan.github_outputs().splitlines())

        self.assertEqual(json.loads(outputs["projects"]), ["chromium"])
        self.assertEqual(json.loads(outputs["specs"]), ["e2e/projects.spec.ts"])
        self.assertEqual(outputs["spec_args"], "e2e/projects.spec.ts")
        self.assertEqual(json.loads(outputs["matrix"]), [{"project": "chromium", "spec_args": "e2e/projects.spec.ts"}])


if __name__ == "__main__":
    unittest.main()
