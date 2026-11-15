"""Invariants for CI and its production runtime that CI itself cannot check."""

from __future__ import annotations

import re
import unittest

from .ci_workflow import (
    BACKEND_DOCKERFILE,
    BACKEND_VENV_ACTION,
    VENV_CREATION,
    backend_venv_jobs,
    load_ci,
    load_yaml,
    run_scripts,
    steps_of,
)


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


if __name__ == "__main__":
    unittest.main()
