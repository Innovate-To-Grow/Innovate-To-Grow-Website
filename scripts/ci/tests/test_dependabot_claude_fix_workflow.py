from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "dependabot-claude-fix.yml"


def load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def workflow_triggers(workflow: dict) -> dict:
    # PyYAML 1.1 parses the unquoted YAML key `on` as the boolean True.
    return workflow.get("on", workflow.get(True, {}))


def named_step(job: dict, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


def python_heredocs(script: str) -> list[str]:
    return [part.split("\nPY", 1)[0] for part in script.split("python - <<'PY'\n")[1:]]


class DependabotClaudeFixWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = load_workflow()
        self.jobs = self.workflow["jobs"]

    def test_only_completed_ci_runs_trigger_the_workflow(self) -> None:
        triggers = workflow_triggers(self.workflow)
        self.assertEqual(set(triggers), {"workflow_run"})
        self.assertEqual(triggers["workflow_run"]["workflows"], ["CI"])
        self.assertEqual(triggers["workflow_run"]["types"], ["completed"])
        self.assertRegex(
            self.workflow["env"]["NPM_SANDBOX_IMAGE"],
            r"^docker\.io/library/node:22\.22\.2-bookworm-slim@sha256:[0-9a-f]{64}$",
        )

        gate_condition = self.jobs["gate"]["if"]
        self.assertIn("workflow_run.conclusion == 'failure'", gate_condition)
        self.assertIn("workflow_run.event == 'pull_request'", gate_condition)
        self.assertIn("workflow_run.run_attempt == 1", gate_condition)

    def test_builtin_tokens_are_read_only_and_scoped_per_job(self) -> None:
        self.assertEqual(self.workflow["permissions"], {})
        read_only = {"actions": "read", "contents": "read", "pull-requests": "read"}
        self.assertEqual(self.jobs["gate"]["permissions"], {**read_only, "issues": "read"})
        self.assertEqual(self.jobs["configuration"]["permissions"], {})
        self.assertEqual(self.jobs["reserve"]["permissions"], {"issues": "write"})
        self.assertEqual(self.jobs["repair"]["permissions"], read_only)
        self.assertEqual(self.jobs["push"]["permissions"], read_only)

    def test_gate_revalidates_identity_freshness_and_required_ci(self) -> None:
        gate_script = named_step(self.jobs["gate"], "Resolve and validate the pull request")["run"]
        for required_guard in (
            'author" == "dependabot[bot]',
            'head_ref" == dependabot/*',
            'head_sha" == "$RUN_HEAD_SHA',
            'has_dependency_label" == "true',
            'ci_result" == "failure',
            'RUN_ACTOR" == "dependabot[bot]',
            'RUN_ACTOR" == "$fixer_login',
            'changes_github_automation" == "false',
            "behind_by == 0",
            "unexpected_commits == 0",
            "dependabot_commits=",
            "actions/workflows/ci.yml/runs?event=pull_request&head_sha=",
            'final_head_sha="$(gh api',
            "attempts < MAX_FIX_ATTEMPTS",
            '.committer.login // "") != $fixer',
            "dependabot-claude-fix-attempt:",
        ):
            with self.subTest(guard=required_guard):
                self.assertIn(required_guard, gate_script)

    def test_claude_gets_no_shell_or_push_credential(self) -> None:
        repair = self.jobs["repair"]
        steps = repair["steps"]
        step_names = [step["name"] for step in steps]
        credential_index = step_names.index("Prepare isolated Anthropic API credential")
        self.assertLess(step_names.index("Install pinned Claude Code"), credential_index)
        self.assertLess(step_names.index("Collect failure context"), credential_index)

        claude = named_step(repair, "Run Claude Code in safe file-only mode")
        script = claude["run"]
        self.assertIn("claude --safe-mode -p", script)
        self.assertNotIn("claude --bare", script)
        self.assertIn('--tools "Read,Glob,Grep,Edit"', script)
        self.assertNotIn('--allowed-tools "Read,Glob,Grep,Edit"', script)
        self.assertIn('--disallowed-tools "Bash,WebFetch,WebSearch,Write,NotebookEdit,Agent,mcp__*"', script)
        self.assertIn("--permission-mode dontAsk", script)
        self.assertIn("--no-session-persistence", script)
        self.assertNotIn("dangerously-skip-permissions", script)
        self.assertNotIn("ANTHROPIC_API_KEY", claude.get("env", {}))
        self.assertNotIn("DEPENDABOT_FIX_TOKEN", str(repair))

        credential = named_step(repair, "Prepare isolated Anthropic API credential")
        self.assertEqual(credential["env"]["ANTHROPIC_API_KEY"], "${{ secrets.ANTHROPIC_API_KEY }}")
        self.assertIn('"apiKeyHelper"', credential["run"])
        self.assertIn('"Read(//proc/**)"', credential["run"])
        self.assertIn('absolute_rule("Edit", auth_dir, "/**")', credential["run"])
        self.assertIn('absolute_rule("Edit", workspace / ".github", "/**")', credential["run"])
        self.assertIn('workspace / "pages" / "package.json"', credential["run"])
        self.assertIn('chmod 400 "$key_path" "$settings_path"', credential["run"])
        self.assertIn('chmod 500 "$auth_dir"', credential["run"])

        cleanup = named_step(repair, "Remove Anthropic credential helper")["run"]
        self.assertIn('rm -rf -- "$auth_dir"', cleanup)

        npm = named_step(repair, "Validate npm companion changes and refresh lockfile")["run"]
        for npm_guard in (
            "cannot add or remove packages",
            "Dependabot target must remain unchanged",
            "only an existing devDependency can be a companion peer",
            "companion is not a required peer of a Dependabot target",
            "existing lock already satisfies every target peer",
            "proposed companion does not satisfy every target peer",
            "companion must use the minimum required peer version",
            'before = json_at(f"{sha}^", MANIFEST)',
            "companion dependency must increase",
            "Dependabot head lockfile",
            "generated lockfile",
            "contains a non-registry package",
            "npm install --package-lock-only --ignore-scripts",
            "npm ci --ignore-scripts --dry-run",
            "Dependabot target lock entry changed",
            "companion lock is not pinned to the proposed minimum",
            "https://registry.npmjs.org/",
            "sha512-",
            "--read-only",
            "--cap-drop ALL",
            "--security-opt no-new-privileges=true",
            "--user 65534:65534",
            '--mount "type=bind,source=${sandbox},target=/work"',
            "NPM_CONFIG_SCRIPT_SHELL=/bin/false",
            "NPM_CONFIG_GIT=/bin/false",
            '"$NPM_SANDBOX_IMAGE"',
            'git diff --quiet "$HEAD_SHA" -- "$lockfile"',
            "follow_symlinks=False",
            "metadata.st_nlink != 1",
            'CANDIDATE_LOCKFILE="$sandbox/package-lock.json"',
            "npm ls --all",
            "its untrusted output was suppressed",
        ):
            with self.subTest(npm_guard=npm_guard):
                self.assertIn(npm_guard, npm)
        self.assertGreaterEqual(npm.count('before = json_at(f"{sha}^", MANIFEST)'), 2)
        self.assertNotIn(
            "ANTHROPIC_API_KEY",
            named_step(repair, "Validate npm companion changes and refresh lockfile").get("env", {}),
        )
        self.assertNotIn("--env GITHUB_", npm)
        self.assertNotIn("$GITHUB_WORKSPACE", npm)
        self.assertEqual(npm.count("--user 65534:65534"), 2)
        self.assertEqual(npm.count("--read-only"), 2)
        self.assertIn('target=/input,readonly"', npm)
        self.assertIn("cp /input/package.json /input/package-lock.json /verify/", npm)

    def test_patch_and_push_are_bounded_and_isolated(self) -> None:
        patch_script = named_step(self.jobs["repair"], "Validate and package the patch")["run"]
        for guard in (
            "new files are not allowed",
            "file deletion is not allowed",
            "binary change is not allowed",
            "symlinks, renames, and mode changes are not allowed",
            "not an allowed production-source path",
            "original Dependabot update file cannot be changed",
            'os.environ["DEPENDABOT_COMMITS"]',
            '"diff-tree"',
            "APPROVED_NPM_TREE_SHA256",
            'npm_paths = {"pages/package.json", "pages/package-lock.json"}',
            '"src/apps/"',
            '"pages/src/"',
            "patch_size <= 2000000",
        ):
            with self.subTest(guard=guard):
                self.assertIn(guard, patch_script)

        push = self.jobs["push"]
        self.assertNotIn("ANTHROPIC_API_KEY", str(push))
        self.assertNotIn("DEPENDABOT_FIX_TOKEN", str(push))

        token_step = named_step(push, "Create short-lived repair App token")
        self.assertEqual(
            token_step["uses"],
            "actions/create-github-app-token@fee1f7d63c2ff003460e3d139729b119787bc349",
        )
        self.assertEqual(token_step["with"]["permission-contents"], "write")
        self.assertEqual(
            token_step["with"]["private-key"],
            "${{ secrets.DEPENDABOT_FIX_APP_PRIVATE_KEY }}",
        )

        push_step = named_step(push, "Commit repair and trigger the next CI run")
        self.assertEqual(push_step["env"]["GH_TOKEN"], "${{ steps.app-token.outputs.token }}")
        self.assertIn('--force-with-lease="refs/heads/${HEAD_REF}:${EXPECTED_HEAD_SHA}"', push_step["run"])
        self.assertIn("HEAD:refs/heads/${HEAD_REF}", push_step["run"])
        self.assertIn("git rev-parse HEAD^", push_step["run"])

        revalidate = named_step(push, "Revalidate the live PR head")["run"]
        self.assertIn("head.sha", revalidate)
        self.assertIn("EXPECTED_HEAD_SHA", revalidate)
        self.assertIn("current_base_sha", revalidate)
        self.assertIn("EXPECTED_BASE_SHA", revalidate)
        self.assertIn("EXPECTED_BASE_REF", revalidate)
        self.assertIn(".base.repo.full_name", revalidate)
        self.assertIn(".draft", revalidate)

    def test_every_pr_checkout_avoids_persisting_credentials(self) -> None:
        checkouts = [
            step
            for job in self.jobs.values()
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        ]
        self.assertEqual(len(checkouts), 2)
        for checkout in checkouts:
            self.assertFalse(checkout["with"]["persist-credentials"])
            self.assertEqual(checkout["with"]["fetch-depth"], 0)

    def test_all_third_party_actions_are_pinned_to_full_commit_shas(self) -> None:
        action_pattern = re.compile(r"^[^@]+@[0-9a-f]{40}$")
        actions = [str(step["uses"]) for job in self.jobs.values() for step in job["steps"] if "uses" in step]
        self.assertGreaterEqual(len(actions), 5)
        for action in actions:
            with self.subTest(action=action):
                self.assertRegex(action, action_pattern)

    def test_embedded_python_and_registry_guard_are_executable(self) -> None:
        blocks = [
            block
            for job in self.jobs.values()
            for step in job["steps"]
            for block in python_heredocs(step.get("run", ""))
        ]
        self.assertGreaterEqual(len(blocks), 7)
        for index, block in enumerate(blocks):
            with self.subTest(block=index):
                compile(block, f"embedded-workflow-python-{index}", "exec")

        registry_block = next(
            block
            for block in blocks
            if "def validate_registry_lock" in block and "Approved npm companion changes" in block
        )
        tree = ast.parse(registry_block)
        guard_module = ast.Module(
            body=[
                node
                for node in tree.body
                if isinstance(node, (ast.Import, ast.ImportFrom))
                or isinstance(node, ast.FunctionDef)
                and node.name == "validate_registry_lock"
            ],
            type_ignores=[],
        )
        namespace: dict = {}
        exec(compile(guard_module, "registry-lock-guard", "exec"), namespace)
        guard = namespace["validate_registry_lock"]
        valid_entry = {
            "resolved": "https://registry.npmjs.org/example/-/example-1.0.0.tgz",
            "integrity": "sha512-AAAA",
        }
        guard({"packages": {"": {}, "node_modules/example": valid_entry}}, label="fixture")
        for invalid_entry in (
            {**valid_entry, "resolved": "git+https://example.com/repository.git"},
            {**valid_entry, "resolved": "https://evil.example/example.tgz"},
            {**valid_entry, "integrity": "sha1-AAAA"},
            {**valid_entry, "link": True},
        ):
            with self.subTest(invalid_entry=invalid_entry):
                with self.assertRaises(SystemExit):
                    guard({"packages": {"": {}, "node_modules/example": invalid_entry}}, label="fixture")


if __name__ == "__main__":
    unittest.main()
