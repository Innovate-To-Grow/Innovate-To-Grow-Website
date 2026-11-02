"""Invariants for CI and its production runtime that CI itself cannot check."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
BACKEND_VENV_ACTION = REPOSITORY_ROOT / ".github" / "actions" / "setup-backend-venv" / "action.yml"
BACKEND_VENV_USES = "./.github/actions/setup-backend-venv"
BACKEND_DOCKERFILE = REPOSITORY_ROOT / "src" / "Dockerfile"
PLAYWRIGHT_CONFIG = REPOSITORY_ROOT / "pages" / "playwright.config.ts"
COVERAGE_FLOORS = REPOSITORY_ROOT / "scripts" / "ci" / "backend_coverage_floors.json"
FLEET_LABEL = "i2g-aws"
DEPENDABOT_CONFIG = REPOSITORY_ROOT / ".github" / "dependabot.yml"
# Any way a job could create a virtualenv itself instead of using setup-backend-venv.
VENV_CREATION = re.compile(r"-m\s+venv\b|\buv\s+venv\b|\bvirtualenv\b")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_ci() -> dict:
    return load_yaml(CI_WORKFLOW)


def steps_of(job: dict) -> list[dict]:
    return job.get("steps") or []


def run_scripts(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in steps_of(job))


def backend_venv_jobs(jobs: dict) -> dict[str, dict]:
    """Jobs that set up the backend virtualenv, mapped to their setup-backend-venv step."""
    return {
        name: step
        for name, job in jobs.items()
        for step in steps_of(job)
        if str(step.get("uses", "")) == BACKEND_VENV_USES
    }


class BackendVirtualenvCacheTests(unittest.TestCase):
    """Guards the fix for the exit-127 flake on run 32223964754.

    The venv cache key used to carry only `env.PYTHON_VERSION` ("3.11"). A
    cached venv hard-codes the interpreter it was built against, so once the
    hosted runner images drifted (3.11.15 -> 3.11.16) the restored
    `.venv/bin/python` symlink dangled and every `.venv/bin/...` call exited
    127. Whether a job hit it depended purely on which runner image it landed
    on, so it struck PRs and main alike, at random. Every backend job now sets
    the venv up through one composite action, so the guarantees are checked
    there, plus that no job builds a venv any other way.
    """

    def setUp(self) -> None:
        self.action_steps = load_yaml(BACKEND_VENV_ACTION)["runs"]["steps"]
        self.jobs = load_ci()["jobs"]

    def _step(self, step_id: str) -> dict:
        return next(step for step in self.action_steps if step.get("id") == step_id)

    def test_the_backend_jobs_all_use_the_shared_virtualenv_setup(self) -> None:
        # Guards against this whole test class silently becoming a no-op.
        self.assertEqual(set(backend_venv_jobs(self.jobs)), {"backend-checks", "django-test-coverage", "e2e"})

    def test_no_job_builds_or_caches_a_virtualenv_around_the_probe(self) -> None:
        for name, job in self.jobs.items():
            with self.subTest(job=name):
                self.assertIsNone(VENV_CREATION.search(run_scripts(job)), "build the venv with setup-backend-venv")
                for step in steps_of(job):
                    path = str((step.get("with") or {}).get("path", ""))
                    self.assertNotIn("venv", path, "only setup-backend-venv may cache a virtualenv")

    def test_the_cache_key_pins_the_resolved_python_patch_version(self) -> None:
        key = self._step("backend-venv-cache")["with"]["key"]

        self.assertIn("steps.setup-python.outputs.python-version", key, "the key must pin the venv's interpreter")
        self.assertNotIn("PYTHON_VERSION", key, "a *_PYTHON_VERSION variable is only the minor series")
        self.assertIn("runner.environment", key, "host and hosted layouts must not share a venv")
        self.assertIn("inputs.cache-label", key, "a job container must not restore a host venv")
        self.assertTrue(str(self._step("setup-python")["uses"]).startswith("actions/setup-python@"))

    def test_a_restored_virtualenv_is_probed_before_it_is_trusted(self) -> None:
        step_ids = [step.get("id") for step in self.action_steps]
        self.assertLess(step_ids.index("backend-venv-cache"), step_ids.index("backend-venv-check"))

        install = next(
            step
            for step in self.action_steps
            if str(step.get("name", "")).startswith("Install")
            and "dependencies" in str(step.get("name", ""))
            and "venv" in str(step.get("run", ""))
        )
        # Reinstall on a *probe* failure, not merely on a cache miss: a cache hit
        # whose interpreter has vanished must still rebuild.
        self.assertIn("steps.backend-venv-check.outputs.usable", install["if"])
        self.assertNotIn("backend-venv-cache.outputs.cache-hit", install["if"])

    def test_only_a_container_job_overrides_the_cache_label(self) -> None:
        for name, step in backend_venv_jobs(self.jobs).items():
            with self.subTest(job=name):
                label = (step.get("with") or {}).get("cache-label")
                if "container" in self.jobs[name]:
                    self.assertTrue(label, "a job container needs its own venv cache label")
                else:
                    self.assertIsNone(label)


class RequiredResultGateTests(unittest.TestCase):
    """The roll-ups that must not pass a run whose required jobs never ran."""

    SKIPPED_IS_FAILURE = {"e2e-required-result", "frontend-required"}

    def setUp(self) -> None:
        self.jobs = load_ci()["jobs"]
        self.rollups = {name: job for name, job in self.jobs.items() if "check_required_results.py" in run_scripts(job)}

    def test_every_rollup_uses_the_shared_checker(self) -> None:
        self.assertEqual(
            set(self.rollups),
            {
                "cli-required-result",
                "frontend-required",
                "backend-required-result",
                "security-required-result",
                "deploy-artifact-result",
                "e2e-required-result",
                "archive-required-result",
                "ci-result",
            },
        )
        for name, job in self.jobs.items():
            with self.subTest(job=name):
                self.assertNotIn('NEEDS_CONTEXT"]', run_scripts(job), "no inline needs-summary heredocs")

    def test_e2e_gate_does_not_pass_a_matrix_that_never_ran(self) -> None:
        """`e2e` gates on the same condition as `e2e-required-result`.

        So it cannot be legitimately path-filtered there, and a "skipped"
        result means an upstream failure cascaded and the device matrix never
        ran. Counting that as a pass is how the required `E2E Required Result`
        check went green on PR #439 with zero E2E coverage behind it.
        """
        for name in self.SKIPPED_IS_FAILURE:
            with self.subTest(job=name):
                self.assertIn("--skipped-is-failure", run_scripts(self.rollups[name]))

    def test_path_filtered_rollups_accept_skipped_jobs(self) -> None:
        for name in set(self.rollups) - self.SKIPPED_IS_FAILURE:
            with self.subTest(job=name):
                self.assertNotIn("--skipped-is-failure", run_scripts(self.rollups[name]))

    def test_ci_result_checks_every_need_it_lists(self) -> None:
        # preflight and changes are needs of ci-result and must be able to fail it.
        script = run_scripts(self.rollups["ci-result"])
        self.assertNotIn("--ignore", script)
        self.assertTrue({"preflight", "changes"} <= set(self.jobs["ci-result"]["needs"]))


class BackendPythonVersionTests(unittest.TestCase):
    """Keep the Django test interpreter aligned with the deployed image."""

    def test_docker_stages_use_the_tested_python_minor(self) -> None:
        tested_version = load_ci()["env"]["BACKEND_PYTHON_VERSION"]
        dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
        stages = {
            stage: version
            for version, stage in re.findall(
                r"^FROM python:(\d+\.\d+)[^\s]* AS (builder|production)$", dockerfile, re.MULTILINE
            )
        }
        self.assertEqual(set(stages), {"builder", "production"})
        for stage, version in stages.items():
            with self.subTest(stage=stage):
                self.assertEqual(version, tested_version)

    def test_backend_jobs_run_with_the_production_python_minor(self) -> None:
        for name, step in backend_venv_jobs(load_ci()["jobs"]).items():
            with self.subTest(job=name):
                self.assertEqual(step["with"]["python-version"], "${{ env.BACKEND_PYTHON_VERSION }}")
        # The shared action is where setup-python actually runs; it must install
        # exactly the version its callers pass in.
        setups = [
            step
            for step in load_yaml(BACKEND_VENV_ACTION)["runs"]["steps"]
            if str(step.get("uses", "")).startswith("actions/setup-python@")
        ]
        self.assertEqual(len(setups), 1)
        self.assertEqual(setups[0]["with"]["python-version"], "${{ inputs.python-version }}")


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


class DependabotCoverageTests(unittest.TestCase):
    """Dependabot must see every action reference, or a moved one stops getting updates."""

    def test_the_github_actions_updates_cover_every_composite_action(self) -> None:
        updates = load_yaml(DEPENDABOT_CONFIG)["updates"]
        entry = next(update for update in updates if update["package-ecosystem"] == "github-actions")
        directories = entry.get("directories") or [entry.get("directory")]
        # "/" covers .github/workflows/ and a root action.yml only.
        self.assertIn("/", directories)
        actions = sorted((REPOSITORY_ROOT / ".github" / "actions").glob("*/action.yml"))
        self.assertTrue(actions)
        for action in actions:
            directory = "/" + action.parent.relative_to(REPOSITORY_ROOT).as_posix()
            with self.subTest(action=directory):
                self.assertTrue(
                    any(directory == pattern or Path(directory).match(pattern) for pattern in directories),
                    f"{directory} is not in the github-actions directories {directories}",
                )


class RoutingTests(unittest.TestCase):
    """Only jobs that are CPU-bound, or need per-leg isolation, wait for an AWS cold boot.

    The AWS fleet starts every job on a fresh machine, about a minute of boot
    before the first step. Jobs shorter than that ran slower on the fleet than
    on a GitHub-hosted runner, and in a burst of runs they queued behind the
    32-machine cap (aws/ci-runners/README.md).
    """

    FLEET_JOBS = {
        "backend-docker-build",
        "backend-image-publish",
        "django-test-coverage",
        "e2e",
        "frontend-prod-build",
        "frontend-unit-coverage",
    }

    def setUp(self) -> None:
        self.jobs = load_ci()["jobs"]

    def test_only_the_heavy_jobs_target_the_fleet(self) -> None:
        on_fleet = {name for name, job in self.jobs.items() if FLEET_LABEL in str(job.get("runs-on", ""))}
        self.assertEqual(on_fleet, self.FLEET_JOBS)

    def test_fleet_jobs_fall_back_to_hosted_runners_for_forks(self) -> None:
        # The webhook guard refuses fork runs, so a fork PR must never ask for the
        # fleet label; with AWS_RUNNERS_ENABLED off, everything runs hosted.
        for name in self.FLEET_JOBS:
            with self.subTest(job=name):
                runs_on = self.jobs[name]["runs-on"]
                self.assertIn("vars.AWS_RUNNERS_ENABLED == 'true'", runs_on)
                self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", runs_on)
                self.assertIn("'[\"ubuntu-24.04\"]'", runs_on)


if __name__ == "__main__":
    unittest.main()
