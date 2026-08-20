"""Invariants for .github/workflows/ci.yml that CI itself cannot check."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def load_ci() -> dict:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def steps_of(job: dict) -> list[dict]:
    return job.get("steps") or []


class BackendVirtualenvCacheTests(unittest.TestCase):
    """Guards the fix for the exit-127 flake on run 32223964754.

    The venv cache key used to carry only `env.PYTHON_VERSION` ("3.11"). A
    cached venv hard-codes the interpreter it was built against, so once the
    hosted runner images drifted (3.11.15 -> 3.11.16) the restored
    `.venv/bin/python` symlink dangled and every `.venv/bin/...` call exited
    127. Whether a job hit it depended purely on which runner image it landed
    on, so it struck PRs and main alike, at random.
    """

    def setUp(self) -> None:
        self.jobs = load_ci()["jobs"]

    def _venv_cache_steps(self):
        for job_name, job in self.jobs.items():
            for step in steps_of(job):
                if step.get("id") == "backend-venv-cache":
                    yield job_name, job, step

    def test_the_suite_still_caches_a_backend_virtualenv(self) -> None:
        # Guards against this whole test class silently becoming a no-op.
        self.assertGreaterEqual(len(list(self._venv_cache_steps())), 5)

    def test_every_cache_key_pins_the_resolved_python_patch_version(self) -> None:
        for job_name, _job, step in self._venv_cache_steps():
            with self.subTest(job=job_name):
                key = step["with"]["key"]
                self.assertIn(
                    "steps.setup-python.outputs.python-version",
                    key,
                    "venv cache key must pin the interpreter it was built against",
                )
                self.assertNotIn(
                    "py${{ env.PYTHON_VERSION }}",
                    key,
                    "env.PYTHON_VERSION is only the 3.11 minor series, not the patch",
                )

    def test_every_caching_job_resolves_that_python_version(self) -> None:
        for job_name, job, _step in self._venv_cache_steps():
            with self.subTest(job=job_name):
                setup_ids = [
                    step.get("id")
                    for step in steps_of(job)
                    if str(step.get("uses", "")).startswith("actions/setup-python@")
                ]
                self.assertIn("setup-python", setup_ids)

    def test_a_restored_virtualenv_is_probed_before_it_is_trusted(self) -> None:
        for job_name, job, _step in self._venv_cache_steps():
            with self.subTest(job=job_name):
                step_ids = [step.get("id") for step in steps_of(job)]
                self.assertIn("backend-venv-check", step_ids)

                install = next(
                    step
                    for step in steps_of(job)
                    if str(step.get("name", "")).startswith("Install")
                    and "dependencies" in str(step.get("name", ""))
                    and "venv" in str(step.get("run", ""))
                )
                # Reinstall on a *probe* failure, not merely on a cache miss:
                # a cache hit whose interpreter has vanished must still rebuild.
                self.assertIn("steps.backend-venv-check.outputs.usable", install["if"])
                self.assertNotIn("backend-venv-cache.outputs.cache-hit", install["if"])


class RequiredResultGateTests(unittest.TestCase):
    def test_e2e_gate_does_not_pass_a_matrix_that_never_ran(self) -> None:
        """`e2e-plan` and `e2e` gate on the same condition as this job.

        So neither can be legitimately path-filtered here, and a "skipped"
        result means an upstream failure cascaded and the device matrix never
        ran. Counting that as a pass is how the required `E2E Required Result`
        check went green on PR #439 with zero E2E coverage behind it.
        """
        job = load_ci()["jobs"]["e2e-required-result"]
        script = "\n".join(str(step.get("run", "")) for step in steps_of(job))

        self.assertIn('ok = {"success"}', script)
        self.assertNotIn('ok = {"success", "skipped"}', script)


if __name__ == "__main__":
    unittest.main()
