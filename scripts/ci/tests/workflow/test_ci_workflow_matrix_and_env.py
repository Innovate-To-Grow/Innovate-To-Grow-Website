from __future__ import annotations

import json
import re
import unittest

from .ci_workflow import COVERAGE_FLOORS, PLAYWRIGHT_CONFIG, REPOSITORY_ROOT, load_ci, steps_of


class MatrixParityTests(unittest.TestCase):
    """PR/push parity: the static matrices cover everything, on every event."""

    def setUp(self) -> None:
        self.jobs = load_ci()["jobs"]

    def test_every_django_app_has_a_matrix_leg_and_a_coverage_floor(self) -> None:
        # A new src/apps/<app>/ would otherwise get no Django test leg and no
        # coverage floor, and nothing else in CI would notice.
        apps_on_disk = sorted(path.parent.name for path in (REPOSITORY_ROOT / "src" / "apps").glob("*/apps.py"))
        floors = json.loads(COVERAGE_FLOORS.read_text(encoding="utf-8"))["apps"]
        strategy_matrix = self.jobs["django-test-coverage"]["strategy"]["matrix"]
        # A matrix `exclude:` would silently drop a leg behind an unchanged list.
        self.assertEqual(set(strategy_matrix), {"app"})
        matrix = strategy_matrix["app"]

        self.assertEqual(sorted(matrix), apps_on_disk)
        self.assertEqual(len(matrix), len(set(matrix)))
        self.assertEqual(sorted(floors), apps_on_disk)

    def test_the_e2e_matrix_runs_every_playwright_project(self) -> None:
        # The full device matrix on every event: PR #433 skipped the iphone14 and
        # ipad legs on its PR and broke them on main (run 32107167026).
        configured = re.findall(r"\{\s*name:\s*'([^']+)'", PLAYWRIGHT_CONFIG.read_text(encoding="utf-8"))
        strategy_matrix = self.jobs["e2e"]["strategy"]["matrix"]
        self.assertEqual(set(strategy_matrix), {"project"})
        matrix = strategy_matrix["project"]

        self.assertEqual(len(configured), 10)
        self.assertEqual(matrix, configured)

    def test_the_matrices_never_fail_fast(self) -> None:
        for name in ("django-test-coverage", "e2e"):
            with self.subTest(job=name):
                self.assertIs(self.jobs[name]["strategy"]["fail-fast"], False)

    def test_the_smoke_and_e2e_jobs_use_the_same_playwright_image(self) -> None:
        self.assertEqual(
            self.jobs["frontend-chromium-smoke"]["container"]["image"], self.jobs["e2e"]["container"]["image"]
        )


class RequestLimiterOffInCiTests(unittest.TestCase):
    """The request limiter (``REQUEST_RATE_LIMITS_ENABLED``) is on in production but must stay off where one client
    on one IP drives the whole site: E2E and the backend container smoke. Its own tests switch it on in-process."""

    LIMITER = "REQUEST_RATE_LIMITS_ENABLED"
    TEST_SETTINGS = "config.settings.environments.test"

    def setUp(self) -> None:
        self.workflow = load_ci()
        self.jobs = self.workflow["jobs"]

    def test_the_jobs_run_the_test_settings(self) -> None:
        self.assertEqual(self.workflow["env"]["DJANGO_SETTINGS_MODULE"], self.TEST_SETTINGS)
        self.assertNotIn("DJANGO_SETTINGS_MODULE", self.jobs["e2e"].get("env", {}))

    def test_e2e_states_the_limiter_off(self) -> None:
        self.assertEqual(self.jobs["e2e"]["env"][self.LIMITER], "false")

    def test_the_container_smoke_states_the_limiter_off(self) -> None:
        script = next(
            str(step["run"])
            for step in steps_of(self.jobs["backend-docker-build"])
            if step.get("name") == "Smoke-test backend Docker runtime"
        )
        self.assertIn(f"-e DJANGO_SETTINGS_MODULE={self.TEST_SETTINGS}", script)
        self.assertIn(f"-e {self.LIMITER}=false", script)

    def test_no_workflow_switches_it_on(self) -> None:
        on = re.compile(rf"{self.LIMITER}\s*[:=]\s*[\"']?(1|true|yes|on)\b", re.IGNORECASE)
        for workflow in sorted((REPOSITORY_ROOT / ".github" / "workflows").glob("*.y*ml")):
            with self.subTest(workflow=workflow.name):
                self.assertIsNone(on.search(workflow.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
