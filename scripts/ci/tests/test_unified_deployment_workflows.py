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

        resolver = production["jobs"]["resolve-ci-release"]
        self.assertIn("workflow_run.conclusion == 'success'", resolver["if"])
        self.assertNotIn("environment", resolver)
        approval = production["jobs"]["approve"]
        self.assertEqual(approval["environment"]["name"], "Production Deployments")
        self.assertEqual(approval["needs"], "resolve-ci-release")
        self.assertEqual(
            set(approval["outputs"]),
            {"deploy_sha", "ci_run_id"},
        )
        environment_jobs = [name for name, job in production["jobs"].items() if "environment" in job]
        self.assertEqual(environment_jobs, ["approve"])
        self.assertFalse(production["concurrency"]["cancel-in-progress"])

    def test_every_component_waits_for_the_same_approval_and_sha(self) -> None:
        production = load_workflow("deploy-production.yml")
        expected = {
            "deploy-status": "./.github/workflows/deploy-status.yml",
            "deploy-backend": "./.github/workflows/deploy-backend.yml",
            "deploy-frontend": "./.github/workflows/deploy-frontend.yml",
            "deploy-archive": "./.github/workflows/deploy-archive.yml",
        }

        for job_name, workflow_path in expected.items():
            with self.subTest(job=job_name):
                job = production["jobs"][job_name]
                needs = job["needs"] if isinstance(job["needs"], list) else [job["needs"]]
                self.assertIn("approve", needs)
                self.assertEqual(job["uses"], workflow_path)
                self.assertEqual(
                    job["with"]["deploy_sha"],
                    "${{ needs.approve.outputs.deploy_sha }}",
                )
                self.assertEqual(job["secrets"], "inherit")

        backend = production["jobs"]["deploy-backend"]
        self.assertFalse(backend["with"]["build_image"])
        self.assertIn("deploy-status", backend["needs"])
        self.assertEqual(
            backend["with"]["status_public_url"],
            "${{ needs.deploy-status.outputs.public_url }}",
        )
        self.assertEqual(
            backend["with"]["status_internal_api_url"],
            "${{ needs.deploy-status.outputs.internal_api_url }}",
        )

        status = production["jobs"]["deploy-status"]
        self.assertFalse(status["with"]["build_assets"])
        self.assertEqual(
            status["with"]["artifact_run_id"],
            "${{ needs.approve.outputs.ci_run_id }}",
        )

    def test_manual_production_release_requires_successful_ci_for_current_main_sha(self) -> None:
        production = load_workflow("deploy-production.yml")
        resolver = production["jobs"]["resolve-ci-release"]
        step = named_step(resolver, "Resolve and verify the successful main CI run")
        script = step["run"]

        self.assertIn('"$EVENT_REF" != "refs/heads/main"', script)
        self.assertIn("git/ref/heads/main", script)
        self.assertIn('"$deploy_sha" != "$main_sha"', script)
        self.assertIn("actions/workflows/ci.yml/runs", script)
        self.assertIn('head_sha="$deploy_sha"', script)
        self.assertIn('.head_branch == "main"', script)
        self.assertIn('.event == "push"', script)
        self.assertIn('.status == "completed"', script)
        self.assertIn('.conclusion == "success"', script)
        self.assertIn(".path == $path", script)
        self.assertIn("head_repository.full_name", script)
        self.assertIn("actions/runs/${ci_run_id}", script)
        self.assertEqual(
            resolver["outputs"]["deploy_sha"],
            "${{ steps.release.outputs.deploy_sha }}",
        )
        self.assertEqual(
            resolver["outputs"]["ci_run_id"],
            "${{ steps.release.outputs.ci_run_id }}",
        )

    def test_component_workflows_are_reusable_and_keep_target_environments(self) -> None:
        expected_environments = {
            "deploy-backend.yml": {"AWS ECS - Prod", "AWS ECS(DEMO) - Prod"},
            "deploy-frontend.yml": {"AWS Amplify - Prod", "AWS Amplify(DEMO) - Prod"},
            "deploy-archive.yml": {"AWS ECS - Archive Prod"},
            "deploy-status.yml": {"AWS Status - Prod"},
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
                checkout_name = "Checkout the approved commit" if name == "deploy-status.yml" else "Checkout code"
                checkout = named_step(deploy, checkout_name)
                self.assertEqual(checkout["with"]["ref"], "${{ inputs.deploy_sha }}")

                environment = deploy["environment"]["name"]
                if "matrix.environment_name" in environment:
                    configured = {target["environment_name"] for target in deploy["strategy"]["matrix"]["include"]}
                else:
                    configured = {environment}
                self.assertEqual(configured, environments)

    def test_status_workflow_promotes_only_the_approved_sha_and_exposes_outputs(self) -> None:
        status = load_workflow("deploy-status.yml")
        trigger = workflow_triggers(status)["workflow_call"]
        self.assertTrue(trigger["inputs"]["deploy_sha"]["required"])
        self.assertEqual(trigger["inputs"]["deploy_sha"]["type"], "string")
        self.assertEqual(trigger["inputs"]["build_assets"]["type"], "boolean")
        self.assertFalse(trigger["inputs"]["build_assets"]["default"])
        self.assertEqual(
            set(trigger["outputs"]),
            {"public_url", "internal_api_url", "distribution_id", "release_sha"},
        )

        self.assertEqual(status["concurrency"]["group"], "deploy-status-production")
        self.assertFalse(status["concurrency"]["cancel-in-progress"])

        deploy = status["jobs"]["deploy"]
        checkout = named_step(deploy, "Checkout the approved commit")
        self.assertEqual(checkout["with"]["ref"], "${{ inputs.deploy_sha }}")
        self.assertEqual(deploy["environment"]["name"], "AWS Status - Prod")
        self.assertIn("status.i2g.ucmerced.edu", deploy["environment"]["url"])

        verify = named_step(deploy, "Verify the exact approved commit and artifact source")
        self.assertIn("^[0-9a-f]{40}$", verify["run"])
        self.assertIn("artifact_sha", verify["run"])
        self.assertIn("$DEPLOY_SHA", verify["run"])
        self.assertIn("artifact_conclusion", verify["run"])
        self.assertIn(".github/workflows/ci.yml", verify["run"])
        self.assertIn('artifact_branch" != "main', verify["run"])

    def test_status_workflow_keeps_region_order_and_bounded_release_rollback(self) -> None:
        status = load_workflow("deploy-status.yml")
        steps = status["jobs"]["deploy"]["steps"]
        step_names = [step.get("name") for step in steps]

        cert_index = step_names.index("Deploy or update the CloudFront certificate stack")
        main_index = step_names.index("Build and deploy the us-west-2 status stack")
        wait_index = step_names.index("Wait for the CloudFront distribution with a bounded poll")
        publish_index = step_names.index("Publish immutable assets before index.html")
        probe_index = step_names.index("Initialize the first status snapshot")
        smoke_index = step_names.index("Smoke check the deployed status service")
        self.assertLess(cert_index, main_index)
        self.assertLess(main_index, wait_index)
        self.assertLess(wait_index, publish_index)
        self.assertLess(publish_index, probe_index)
        self.assertLess(probe_index, smoke_index)

        cert = named_step(status["jobs"]["deploy"], "Deploy or update the CloudFront certificate stack")
        self.assertIn('--region "$STATUS_EAST_REGION"', cert["run"])
        main = named_step(status["jobs"]["deploy"], "Build and deploy the us-west-2 status stack")
        self.assertIn('--region "$STATUS_REGION"', main["run"])
        self.assertIn("CertificateArn=$CERTIFICATE_ARN", main["run"])

        wait = named_step(status["jobs"]["deploy"], "Wait for the CloudFront distribution with a bounded poll")
        self.assertIn("seq 1 120", wait["run"])
        publish = named_step(status["jobs"]["deploy"], "Publish immutable assets before index.html")
        self.assertLess(publish["run"].index("status/dist/assets"), publish["run"].index("status/dist/index.html"))
        self.assertNotIn("sync --delete", publish["run"])
        self.assertIn("immutable", publish["run"])

        rollback = named_step(status["jobs"]["deploy"], "Restore the previous index after a post-publish failure")
        self.assertIn("PREVIOUS_INDEX_VERSION", rollback["run"])
        self.assertIn("steps.smoke.outcome == 'failure'", rollback["if"])
        self.assertIn("steps.probe.outcome == 'failure'", rollback["if"])
        self.assertIn("steps.publish-invalidation.outcome == 'failure'", rollback["if"])
        self.assertIn("create-invalidation", rollback["run"])

        retirement = named_step(status["jobs"]["deploy"], "Mark unreferenced hashed assets for delayed retirement")
        self.assertEqual(retirement["if"], "${{ steps.smoke.outcome == 'success' }}")
        self.assertTrue(retirement["continue-on-error"])
        self.assertIn("PREVIOUS_INDEX_VERSION", retirement["run"])
        self.assertIn('"status-retire", "Value": "true"', retirement["run"])
        self.assertIn("delete_object_tagging", retirement["run"])
        self.assertIn("s3.copy_object", retirement["run"])
        self.assertIn("already_retired", retirement["run"])
        self.assertIn('MetadataDirective="COPY"', retirement["run"])

    def test_status_smoke_covers_public_private_and_signed_paths(self) -> None:
        status = load_workflow("deploy-status.yml")
        smoke = named_step(status["jobs"]["deploy"], "Smoke check the deployed status service")["run"]

        self.assertIn("get-bucket-location", smoke)
        self.assertIn("direct_code", smoke)
        self.assertIn('"403"', smoke)
        self.assertIn("status-v1.schema.json", smoke)
        self.assertIn("production-website", smoke)
        self.assertIn("stale-if-error=900", smoke)
        self.assertIn("unsigned_code", smoke)
        self.assertIn("SigV4Auth", smoke)
        self.assertIn('get("version") != os.environ["RELEASE_SHA"]', smoke)
        self.assertIn("seq 1 30", smoke)
        self.assertIn("seq 1 42", smoke)

    def test_status_ci_is_credential_free_and_gates_ci_result(self) -> None:
        ci = load_workflow("ci.yml")
        status_jobs = {
            "status-frontend",
            "status-browser",
            "status-lambda",
            "status-infrastructure",
        }
        self.assertTrue(status_jobs <= set(ci["jobs"]))

        gate = ci["jobs"]["status-required-result"]
        self.assertTrue(status_jobs <= set(gate["needs"]))
        self.assertIn("status-required-result", ci["jobs"]["ci-result"]["needs"])
        self.assertEqual(ci["env"]["NODE_VERSION"], "22.22.2")
        self.assertEqual(ci["env"]["STATUS_PYTHON_VERSION"], "3.13")

        for job_name in status_jobs:
            with self.subTest(job=job_name):
                serialized = yaml.safe_dump(ci["jobs"][job_name])
                self.assertNotIn("configure-aws-credentials", serialized)
                self.assertNotIn("AWS_ACCESS_KEY_ID", serialized)
                self.assertIn("needs.changes.outputs.status", serialized)

        frontend = ci["jobs"]["status-frontend"]
        upload = named_step(frontend, "Upload status production assets")
        self.assertEqual(upload["with"]["name"], "status-dist-production")
        infrastructure = ci["jobs"]["status-infrastructure"]
        lint_install = named_step(infrastructure, "Install CloudFormation lint tools")["run"]
        self.assertIn('"cfn-lint==1.55.1"', lint_install)
        self.assertIn('"PyYAML==6.0.3"', lint_install)
        self.assertNotIn('"PyYAML==6.0.2"', lint_install)
        self.assertIn("sam build", named_step(infrastructure, "Build the status SAM application")["run"])
        self.assertIn("--lint", named_step(infrastructure, "Validate the status SAM template")["run"])
        self.assertIn("cfn-lint", named_step(infrastructure, "Lint both regional CloudFormation templates")["run"])
        self.assertIn(
            "validate_status_infrastructure.py",
            named_step(infrastructure, "Assert status infrastructure security invariants")["run"],
        )

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
