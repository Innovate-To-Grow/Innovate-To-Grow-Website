from __future__ import annotations

import re
import unittest
from pathlib import Path

from .ci_workflow import (
    DEPENDABOT_CONFIG,
    DEPLOY_ARCHIVE_WORKFLOW,
    REPOSITORY_ROOT,
    TRIVY_ACTION,
    TRIVY_RELEASES,
    WORKFLOW_DIRECTORY,
    load_ci,
    load_yaml,
    steps_of,
    trivy_scans,
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


class RunnerTests(unittest.TestCase):
    """Every workflow job runs on a GitHub-hosted runner.

    The AWS self-hosted runner fleet (aws/ci-runners) was removed in 2026-11. A job that
    asked for its labels again would wait in the queue for a runner that no longer exists.
    """

    def test_no_job_asks_for_a_self_hosted_runner(self) -> None:
        for path in sorted(WORKFLOW_DIRECTORY.glob("*.yml")):
            for name, job in (load_yaml(path).get("jobs") or {}).items():
                with self.subTest(workflow=path.name, job=name):
                    runs_on = str(job.get("runs-on", ""))
                    for marker in ("self-hosted", "i2g-aws", "AWS_RUNNERS_ENABLED"):
                        self.assertNotIn(marker, runs_on)


class ActionPinningTests(unittest.TestCase):
    """Every action is pinned to a full commit SHA, with the release it was in.

    A tag can be moved to other code at any time; several of these actions run
    with `id-token: write` against AWS. The `# vX.Y.Z` comment is what lets
    Dependabot keep the pins current.
    """

    USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$", re.MULTILINE)
    PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
    VERSION_COMMENT = re.compile(r"^\s+# v\d+(?:\.\d+)*$")

    def test_every_action_is_pinned_to_a_commit_sha(self) -> None:
        files = sorted((REPOSITORY_ROOT / ".github" / "workflows").glob("*.yml"))
        files += sorted((REPOSITORY_ROOT / ".github" / "actions").glob("*/action.yml"))
        references = 0
        for path in files:
            for match in self.USES.finditer(path.read_text(encoding="utf-8")):
                reference, rest = match.group(1), match.group(2)
                if reference.startswith("./"):
                    continue  # actions in this repository
                references += 1
                with self.subTest(file=path.name, uses=reference):
                    self.assertRegex(reference, self.PINNED)
                    self.assertRegex(rest, self.VERSION_COMMENT)
        self.assertGreater(references, 50, "guards against this test silently matching nothing")


class ArchiveImageScanTests(unittest.TestCase):
    """CI scans the archive image the way the production deploy will, before anyone approves a deploy.

    The archive image used to be built and scanned only inside deploy-archive.yml, after the approval and in
    parallel with the backend rollout. A fixable zlib1g CVE in its base image then failed every approved
    Deploy Production run from 2026-11-11 while main CI stayed green. CI must fail on what that scan fails on.
    """

    # Each workflow scans its own tag, and the output format does not change the verdict.
    MAY_DIFFER = {"image-ref", "format"}

    def setUp(self) -> None:
        self.jobs = load_ci()["jobs"]
        self.ci = self.jobs["archive-docker-build"]
        self.deploy = load_yaml(DEPLOY_ARCHIVE_WORKFLOW)["jobs"]["deploy"]

    def test_ci_builds_the_context_the_deploy_ships(self) -> None:
        for job in (self.ci, self.deploy):
            with self.subTest(job=job["name"]):
                builds = [
                    str(step["run"]) for step in steps_of(job) if str(step.get("run", "")).startswith("docker build")
                ]
                self.assertEqual(len(builds), 1, builds)
                # No layer cache: the image's apt-get upgrade must take the current Debian security updates.
                self.assertNotIn("--cache-from", builds[0])
                self.assertTrue(builds[0].rstrip().endswith(" archive/page/"), builds[0])

    def test_ci_scans_with_the_deploy_settings(self) -> None:
        ((ci,), (deploy,)) = (trivy_scans(self.ci), trivy_scans(self.deploy))
        settings = {key: value for key, value in deploy["with"].items() if key not in self.MAY_DIFFER}

        self.assertEqual({key: value for key, value in ci["with"].items() if key not in self.MAY_DIFFER}, settings)
        self.assertEqual((settings["severity"], settings["exit-code"]), ("CRITICAL,HIGH", "1"))
        self.assertIs(settings["ignore-unfixed"], True)

    def test_a_failed_scan_fails_ci_result(self) -> None:
        self.assertEqual(self.ci["if"], "${{ needs.changes.outputs.archive == 'true' }}")
        self.assertIn("archive-docker-build", self.jobs["archive-required-result"]["needs"])
        self.assertIn("archive-required-result", self.jobs["ci-result"]["needs"])


class TrivyInstallTests(unittest.TestCase):
    """Every Trivy scan runs a binary installed from GitHub releases, not trivy-action's installer.

    That installer downloads through get.trivy.dev, which the runners could not reach on 2026-11-03/04 (UTC): it
    failed the backend image scan in CI and the archive deploy's scan. scripts/ci/tool_versions/ keeps
    the installed TRIVY_VERSION equal everywhere.
    """

    def test_every_trivy_step_uses_the_binary_installed_before_it(self) -> None:
        scans = 0
        for path in sorted(WORKFLOW_DIRECTORY.glob("*.yml")):
            for name, job in (load_yaml(path).get("jobs") or {}).items():
                steps = steps_of(job)
                for index, step in enumerate(steps):
                    if not str(step.get("uses", "")).startswith(TRIVY_ACTION):
                        continue
                    scans += 1
                    with self.subTest(workflow=path.name, job=name, step=step.get("name")):
                        self.assertIs((step.get("with") or {}).get("skip-setup-trivy"), True)
                        installs = [prior for prior in steps[:index] if TRIVY_RELEASES in str(prior.get("run", ""))]
                        self.assertEqual(len(installs), 1)
        # The backend scan and its table re-render, the archive CI scan and the archive deploy's scan.
        self.assertGreaterEqual(scans, 4, "guards against this test silently matching nothing")


if __name__ == "__main__":
    unittest.main()
