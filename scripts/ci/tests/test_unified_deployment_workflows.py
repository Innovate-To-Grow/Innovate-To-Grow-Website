from __future__ import annotations

import unittest
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_DIRECTORY = REPOSITORY_ROOT / ".github" / "workflows"


def load_workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOW_DIRECTORY / name).read_text(encoding="utf-8"))


def workflow_triggers(workflow: dict) -> dict:
    # PyYAML 1.1 parses the unquoted YAML key `on` as the boolean True.
    return workflow.get("on", workflow.get(True, {}))


def named_step(job: dict, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


class UnifiedDeploymentWorkflowTests(unittest.TestCase):
    def test_orchestrator_owns_the_only_ci_completion_trigger_and_approval(self) -> None:
        production = load_workflow("deploy-production.yml")
        triggers = workflow_triggers(production)

        self.assertEqual(set(triggers), {"workflow_run", "workflow_dispatch"})
        self.assertEqual(triggers["workflow_run"]["workflows"], ["CI"])
        self.assertEqual(triggers["workflow_run"]["branches"], ["main"])

        approval = production["jobs"]["approve"]
        self.assertEqual(approval["environment"]["name"], "Production Deployments")
        self.assertIn("workflow_run.conclusion == 'success'", approval["if"])
        self.assertIn("github.ref == 'refs/heads/main'", approval["if"])
        self.assertFalse(production["concurrency"]["cancel-in-progress"])

    def test_every_component_waits_for_the_same_approval_and_sha(self) -> None:
        production = load_workflow("deploy-production.yml")
        expected = {
            "deploy-backend": "./.github/workflows/deploy-backend.yml",
            "deploy-frontend": "./.github/workflows/deploy-frontend.yml",
            "deploy-archive": "./.github/workflows/deploy-archive.yml",
        }

        for job_name, workflow_path in expected.items():
            with self.subTest(job=job_name):
                job = production["jobs"][job_name]
                self.assertEqual(job["needs"], "approve")
                self.assertEqual(job["uses"], workflow_path)
                deploy_sha = job["with"]["deploy_sha"]
                self.assertIn("github.event.workflow_run.head_sha", deploy_sha)
                self.assertIn("github.sha", deploy_sha)
                self.assertEqual(job["secrets"], "inherit")

        backend = production["jobs"]["deploy-backend"]
        self.assertIn(
            "github.event_name == 'workflow_dispatch'",
            backend["with"]["build_image"],
        )

    def test_component_workflows_are_reusable_and_keep_target_environments(self) -> None:
        expected_environments = {
            "deploy-backend.yml": {"AWS ECS - Prod", "AWS ECS(DEMO) - Prod"},
            "deploy-frontend.yml": {"AWS Amplify - Prod", "AWS Amplify(DEMO) - Prod"},
            "deploy-archive.yml": {"AWS ECS - Archive Prod"},
        }

        for name, environments in expected_environments.items():
            with self.subTest(workflow=name):
                workflow = load_workflow(name)
                triggers = workflow_triggers(workflow)
                self.assertEqual(set(triggers), {"workflow_call"})
                deploy_sha = triggers["workflow_call"]["inputs"]["deploy_sha"]
                self.assertTrue(deploy_sha["required"])
                self.assertEqual(deploy_sha["type"], "string")
                self.assertFalse(workflow["concurrency"]["cancel-in-progress"])

                deploy = workflow["jobs"]["deploy"]
                checkout = named_step(deploy, "Checkout code")
                self.assertEqual(checkout["with"]["ref"], "${{ inputs.deploy_sha }}")

                environment = deploy["environment"]["name"]
                if "matrix.environment_name" in environment:
                    configured = {target["environment_name"] for target in deploy["strategy"]["matrix"]["include"]}
                else:
                    configured = {environment}
                self.assertEqual(configured, environments)

    def test_backend_promotes_ci_image_or_builds_for_manual_dispatch(self) -> None:
        backend = load_workflow("deploy-backend.yml")
        deploy = backend["jobs"]["deploy"]
        resolve = named_step(deploy, "Resolve Docker image URI")
        pull = named_step(deploy, "Pull published Docker image")
        build = named_step(deploy, "Build and tag Docker image")
        push = named_step(deploy, "Push Docker image to ECR")

        self.assertEqual(resolve["env"]["DEPLOY_SHA"], "${{ inputs.deploy_sha }}")
        self.assertIn("${DEPLOY_SHA}", resolve["run"])
        self.assertEqual(pull["if"], "${{ !inputs.build_image }}")
        self.assertEqual(build["if"], "${{ inputs.build_image }}")
        self.assertEqual(push["if"], "${{ inputs.build_image }}")

    def test_archive_tags_the_approved_sha(self) -> None:
        archive = load_workflow("deploy-archive.yml")
        build = named_step(archive["jobs"]["deploy"], "Build, tag, and push Docker image")

        self.assertEqual(build["env"]["IMAGE_TAG"], "${{ inputs.deploy_sha }}")

    def test_github_deployment_pointer_links_to_canonical_docs(self) -> None:
        pointer = (REPOSITORY_ROOT / ".github" / "DEPLOYMENT.md").read_text(encoding="utf-8")

        self.assertIn("../docs/deployment/production.md", pointer)


if __name__ == "__main__":
    unittest.main()
