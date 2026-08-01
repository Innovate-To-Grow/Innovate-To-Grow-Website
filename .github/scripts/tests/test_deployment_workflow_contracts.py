from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def load_workflow(name: str) -> dict:
    path = REPOSITORY_ROOT / ".github/workflows" / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def step_runs(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


def step_uses(job: dict) -> list[str]:
    return [str(step["uses"]) for step in job["steps"] if "uses" in step]


def named_step(job: dict, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


class DeploymentWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ci = load_workflow("ci.yml")

    def assert_scanned_image_is_promoted(
        self,
        *,
        build_job: str,
        publish_job: str,
        local_image_name: str,
        artifact_prefix: str,
    ) -> None:
        build = self.ci["jobs"][build_job]
        publish = self.ci["jobs"][publish_job]
        build_runs = step_runs(build)
        publish_runs = step_runs(publish)
        publish_uses = step_uses(publish)

        self.assertIn(f'docker save --output "${{{{ runner.temp }}}}/{artifact_prefix}.tar"', build_runs)
        self.assertIn(f"{local_image_name}:${{{{ github.sha }}}}", build_runs)
        self.assertTrue(any(use.startswith("actions/upload-artifact@") for use in step_uses(build)))

        self.assertTrue(any(use.startswith("actions/download-artifact@") for use in publish_uses))
        self.assertFalse(any(use.startswith("docker/build-push-action@") for use in publish_uses))
        self.assertIn(f"{artifact_prefix}.tar", publish_runs)
        self.assertIn("docker load --input", publish_runs)
        self.assertIn(f'source_image="{local_image_name}:${{GITHUB_SHA}}"', publish_runs)
        self.assertIn("docker tag", publish_runs)
        self.assertIn("docker push", publish_runs)
        self.assertIn("RepoDigests", publish_runs)
        self.assertIn('"sha": os.environ["GITHUB_SHA"]', publish_runs)
        self.assertIn('"repository": os.environ["ECR_REPOSITORY"]', publish_runs)
        self.assertIn('"digest": os.environ["IMAGE_DIGEST"]', publish_runs)
        self.assertIn(
            f"{artifact_prefix}-manifest-${{{{ github.sha }}}}",
            str(publish),
        )
        self.assertIn("retention-days", str(publish))

    def test_backend_publish_promotes_the_scanned_image(self) -> None:
        self.assert_scanned_image_is_promoted(
            build_job="backend-docker-build",
            publish_job="backend-image-publish",
            local_image_name="itg-backend-ci",
            artifact_prefix="backend-image",
        )

    def test_archive_publish_promotes_the_scanned_image(self) -> None:
        self.assert_scanned_image_is_promoted(
            build_job="archive-docker-build",
            publish_job="archive-image-publish",
            local_image_name="itg-archive-ci",
            artifact_prefix="archive-image",
        )

    def test_container_deploys_require_ci_captured_digest_provenance(self) -> None:
        break_glass = load_workflow("deploy-break-glass.yml")
        for component in ("backend", "archive"):
            with self.subTest(component=component):
                deploy = load_workflow(f"deploy-{component}.yml")
                triggers = deploy.get("on", deploy.get(True))
                ci_run_input = triggers["workflow_call"]["inputs"]["ci_run_id"]
                self.assertTrue(ci_run_input["required"])

                gate = deploy["jobs"]["gate"]
                gate_run = named_step(gate, "Validate SHA and inspect the triggering CI run")["run"]
                self.assertIn("ci_run_id must be a positive GitHub Actions run ID", gate_run)
                self.assertIn('run_path" != ".github/workflows/ci.yml"', gate_run)
                self.assertIn(f"{component.title()} Image Publish", gate_run)
                self.assertIn("ci-run-id=$CI_RUN_ID", gate_run)

                job = deploy["jobs"]["deploy"]
                download = named_step(
                    job,
                    f"Download CI-captured {component} image provenance",
                )
                self.assertTrue(str(download["uses"]).startswith("actions/download-artifact@"))
                self.assertEqual(download["with"]["run-id"], "${{ env.CI_RUN_ID }}")
                self.assertEqual(download["with"]["github-token"], "${{ github.token }}")

                validation = named_step(
                    job,
                    f"Validate {component} image provenance",
                )["run"]
                self.assertIn('set(manifest) != {"sha", "repository", "digest"}', validation)
                self.assertIn('manifest["sha"] != os.environ["DEPLOY_SHA"]', validation)
                self.assertIn(
                    'manifest["repository"] != os.environ["ECR_REPOSITORY"]',
                    validation,
                )

                resolve = named_step(
                    job,
                    f"Verify the CI-published {component} image digest",
                )["run"]
                self.assertIn('current_digest" != "$CAPTURED_DIGEST', resolve)
                self.assertIn("@${CAPTURED_DIGEST}", resolve)

                reusable = break_glass["jobs"][f"deploy-{component}"]
                self.assertEqual(
                    reusable["with"]["ci_run_id"],
                    "${{ needs.authorize.outputs.ci_run_id }}",
                )

    def test_break_glass_passes_only_declared_component_secrets(self) -> None:
        break_glass = load_workflow("deploy-break-glass.yml")
        expected = {
            "backend": {
                "DB_PASSWORD_SECRET_ARN",
                "DJANGO_SECRET_KEY_SECRET_ARN",
                "DJANGO_SUPERUSER_EMAIL",
                "DJANGO_SUPERUSER_PASSWORD_SECRET_ARN",
                "DJANGO_SUPERUSER_USERNAME",
                "ECS_EXECUTION_ROLE_ARN",
                "ECS_TASK_ROLE_ARN",
                "REDIS_URL_SECRET_ARN",
            },
            "frontend": {"AMPLIFY_APP_ID"},
            "archive": {
                "ECS_EXECUTION_ROLE_ARN",
                "ECS_TASK_ROLE_ARN",
                "SHEETS_API_KEY_SECRET_ARN",
            },
        }

        for component, names in expected.items():
            with self.subTest(component=component):
                deploy = load_workflow(f"deploy-{component}.yml")
                triggers = deploy.get("on", deploy.get(True))
                declared = triggers["workflow_call"]["secrets"]
                passed = break_glass["jobs"][f"deploy-{component}"]["secrets"]

                self.assertEqual(set(declared), names)
                self.assertEqual(set(passed), names)
                self.assertTrue(all(config["required"] is False for config in declared.values()))
                self.assertTrue(
                    all(value == f"${{{{ secrets.{name} }}}}" for name, value in passed.items()),
                )

    def test_archive_smoke_checks_content_types_and_semantic_payloads(self) -> None:
        deploy = load_workflow("deploy-archive.yml")
        smoke = named_step(
            deploy["jobs"]["deploy"],
            "Smoke check readiness, page, and Sheets proxy",
        )["run"]
        self.assertIn("content-type: application/json", smoke)
        self.assertIn("content-type: text/html", smoke)
        self.assertIn('health != {"status": "ok"}', smoke)
        self.assertIn('payload.get("values")', smoke)

    def test_demo_admin_bootstrap_is_explicitly_confirmed(self) -> None:
        deploy = load_workflow("deploy-backend.yml")
        self.assertIn(
            "python manage.py ensure_default_admin --yes",
            step_runs(deploy["jobs"]["deploy"]),
        )

    def test_worker_rolls_out_before_web_queueing_and_heartbeat_gates_web(self) -> None:
        deploy = load_workflow("deploy-backend.yml")
        job = deploy["jobs"]["deploy"]
        environment = job["env"]
        self.assertIn("vars.BACKGROUND_JOBS_ENABLED", environment["BACKGROUND_WORKER_ENABLED"])
        self.assertIn("matrix.metrics_namespace", environment["BACKGROUND_JOB_METRICS_NAMESPACE"])

        validation = named_step(job, "Validate deployment configuration")["run"]
        self.assertIn(
            "BACKGROUND_JOBS_ENABLED requires BACKGROUND_WORKER_ENABLED=true",
            validation,
        )

        worker = named_step(job, "Register and deploy the single background worker")
        heartbeat = named_step(job, "Verify a fresh CloudWatch worker heartbeat")
        web = named_step(job, "Register and deploy the web task definition")
        self.assertIn("worker-enabled", worker["if"])
        self.assertIn("worker-enabled", heartbeat["if"])
        self.assertIn("aws cloudwatch get-metric-statistics", heartbeat["run"])
        self.assertIn('--region "$AWS_S3_REGION_NAME"', heartbeat["run"])
        self.assertIn("--metric-name WorkerHeartbeat", heartbeat["run"])
        self.assertIn("BACKGROUND_WORKER_HEARTBEAT_MAX_AGE_SECONDS", heartbeat["run"])
        self.assertIn("required_bucket_epoch", heartbeat["run"])
        self.assertIn('latest_epoch" -ge "$required_bucket_epoch', heartbeat["run"])

        names = [step.get("name") for step in job["steps"]]
        self.assertLess(names.index(worker["name"]), names.index(heartbeat["name"]))
        self.assertLess(names.index(heartbeat["name"]), names.index(web["name"]))

    def test_worker_metrics_are_isolated_by_deployment_target(self) -> None:
        deploy = load_workflow("deploy-backend.yml")
        targets = deploy["jobs"]["deploy"]["strategy"]["matrix"]["include"]
        namespaces = {target["target"]: target["metrics_namespace"] for target in targets}
        self.assertEqual(set(namespaces), {"prod", "demo"})
        self.assertNotEqual(namespaces["prod"], namespaces["demo"])

    def test_frontend_requires_deploy_time_cms_frame_sources(self) -> None:
        deploy = load_workflow("deploy-frontend.yml")
        job = deploy["jobs"]["deploy"]
        self.assertIn("AMPLIFY_CSP_FRAME_SOURCES", job["env"])
        runs = step_runs(job)
        self.assertIn("render_amplify_headers.py", runs)
        self.assertIn("--frame-sources", runs)

    def test_backend_jobs_cache_wheels_not_virtualenvs(self) -> None:
        backend_jobs = (
            "backend-db-migration",
            "backend-static-and-prod-check",
            "django-test-coverage",
            "cli-admin-coverage",
            "e2e",
        )
        for job_name in backend_jobs:
            with self.subTest(job=job_name):
                job = self.ci["jobs"][job_name]
                setup_python = next(
                    step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/setup-python@")
                )
                self.assertEqual(setup_python["with"]["cache"], "pip")
                self.assertEqual(
                    setup_python["with"]["cache-dependency-path"],
                    "src/requirements/local.lock.txt",
                )
                for step in job["steps"]:
                    self.assertNotEqual(step.get("with", {}).get("path"), "src/.venv")

    def test_backend_csp_mode_is_a_validated_rendered_deployment_input(self) -> None:
        deploy = load_workflow("deploy-backend.yml")
        job = deploy["jobs"]["deploy"]
        self.assertIn("vars.CSP_REPORT_ONLY", job["env"]["CSP_REPORT_ONLY"])
        validation = named_step(job, "Validate deployment configuration")["run"]
        self.assertIn('normalize_boolean "$CSP_REPORT_ONLY"', validation)
        self.assertIn(
            'echo "CSP_REPORT_ONLY=$csp_report_only" >> "$GITHUB_ENV"',
            validation,
        )

        task_template = json.loads(
            (REPOSITORY_ROOT / "aws/task-definition.json").read_text(
                encoding="utf-8",
            )
        )
        environment = {item["name"]: item["value"] for item in task_template["containerDefinitions"][0]["environment"]}
        self.assertEqual(environment["CSP_REPORT_ONLY"], "__CSP_REPORT_ONLY__")

    def test_playwright_is_a_required_aggregate_gate(self) -> None:
        e2e = self.ci["jobs"]["e2e"]
        self.assertNotIn("continue-on-error", e2e)

        required = self.ci["jobs"]["e2e-required-result"]
        self.assertIn("e2e", required["needs"])
        self.assertNotIn("continue-on-error", required)
        self.assertIn(
            "e2e-required-result",
            self.ci["jobs"]["ci-result"]["needs"],
        )

    def test_live_playwright_leg_owns_the_backend_harness(self) -> None:
        e2e = self.ci["jobs"]["e2e"]
        self.assertIn("postgres", e2e["services"])

        for step_name in (
            "Set up Python",
            "Install backend dependencies",
            "Prepare backend database",
            "Seed admin E2E data",
            "Start backend",
        ):
            with self.subTest(step=step_name):
                self.assertIn(
                    "matrix.project == 'live-chromium'",
                    named_step(e2e, step_name)["if"],
                )

        self.assertNotIn("if", named_step(e2e, "Start frontend preview"))

    def test_security_policy_changes_trigger_ci_and_reach_every_trivy_scan(self) -> None:
        workflow_text = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow_text.count('- ".github/scripts/**"'), 2)
        self.assertEqual(
            workflow_text.count('- ".github/security-exceptions.json"'),
            2,
        )

        for job_name in ("backend-docker-build", "archive-docker-build"):
            with self.subTest(job=job_name):
                job = self.ci["jobs"][job_name]
                policy_step = named_step(job, "Load Trivy security exceptions")
                self.assertIn("--scanner trivy", policy_step["run"])
                for step in job["steps"]:
                    if str(step.get("uses", "")).startswith("aquasecurity/trivy-action@"):
                        self.assertEqual(
                            step["with"]["trivyignores"],
                            "${{ steps.trivy-exceptions.outputs.ids }}",
                        )


if __name__ == "__main__":
    unittest.main()
