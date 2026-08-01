from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RENDERER_PATH = REPOSITORY_ROOT / ".github/scripts/render_backend_task_definitions.py"
SPEC = importlib.util.spec_from_file_location("render_backend_task_definitions", RENDERER_PATH)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class RenderBackendTaskDefinitionsTests(unittest.TestCase):
    def deployment_environment(self) -> dict[str, str]:
        return {
            "BACKGROUND_JOBS_ENABLED": "true",
            "BACKGROUND_WORKER_ENABLED": "true",
            "CSP_REPORT_ONLY": "false",
            "FRONTEND_URL": "https://app.example.com",
            "BACKEND_URL": "https://api.example.com",
            "API_BASE_URL": "https://api.example.com/api",
            "AWS_STORAGE_BUCKET_NAME": "itg-static-example",
            "AWS_S3_REGION_NAME": "us-west-2",
            "ECS_TASK_FAMILY": "itg-backend",
            "ECS_WORKER_TASK_FAMILY": "itg-worker",
            "ECS_EXECUTION_ROLE_ARN": "arn:aws:iam::123456789012:role/ecs-execution",
            "ECS_TASK_ROLE_ARN": "arn:aws:iam::123456789012:role/ecs-task",
            "IMAGE_URI": "123456789012.dkr.ecr.us-west-2.amazonaws.com/itg-backend@sha256:abc",
            "ECS_WORKER_LOG_GROUP": "/ecs/itg-worker",
            "DJANGO_SECRET_KEY_SECRET_ARN": ("arn:aws:secretsmanager:us-west-2:123456789012:secret:django-secret"),
            "DB_PASSWORD_SECRET_ARN": "arn:aws:ssm:us-west-2:123456789012:parameter/db-password",
            "REDIS_URL_SECRET_ARN": "arn:aws:ssm:us-west-2:123456789012:parameter/redis-url",
            "DB_NAME": "itg",
            "DB_USER": "itg",
            "DB_HOST": "database.example.com",
        }

    def test_worker_receives_all_settings_required_by_production(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            worker_output = Path(temporary_directory) / "worker.json"
            with patch.dict(os.environ, self.deployment_environment(), clear=True):
                runtime_environment = renderer.required_runtime_environment()
                renderer.render_worker(
                    REPOSITORY_ROOT / "aws/worker-task-definition.json",
                    worker_output,
                    runtime_environment,
                )

            task_definition = json.loads(worker_output.read_text(encoding="utf-8"))
            environment = {
                item["name"]: item["value"] for item in task_definition["containerDefinitions"][0]["environment"]
            }
            self.assertEqual(
                environment["DJANGO_ALLOWED_HOSTS"],
                "api.example.com,app.example.com,.cloudfront.net,.elb.amazonaws.com",
            )
            self.assertEqual(environment["BACKEND_URL"], "https://api.example.com")
            self.assertEqual(environment["FRONTEND_URL"], "https://app.example.com")
            self.assertEqual(environment["AWS_STORAGE_BUCKET_NAME"], "itg-static-example")
            self.assertEqual(environment["AWS_S3_REGION_NAME"], "us-west-2")
            self.assertEqual(environment["BACKGROUND_JOBS_ENABLED"], "true")

    def test_worker_can_roll_out_while_web_queueing_remains_disabled(self) -> None:
        environment = self.deployment_environment()
        environment["BACKGROUND_JOBS_ENABLED"] = "false"
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            web_output = output_directory / "web.json"
            one_off_output = output_directory / "one-off.json"
            worker_output = output_directory / "worker.json"
            with patch.dict(os.environ, environment, clear=True):
                runtime_environment = renderer.required_runtime_environment()
                renderer.render_web(
                    REPOSITORY_ROOT / "aws/task-definition.json",
                    web_output,
                    one_off_output,
                    runtime_environment,
                )
                renderer.render_worker(
                    REPOSITORY_ROOT / "aws/worker-task-definition.json",
                    worker_output,
                    runtime_environment,
                )

            web_task = json.loads(web_output.read_text(encoding="utf-8"))
            worker_task = json.loads(worker_output.read_text(encoding="utf-8"))
            web_environment = {
                item["name"]: item["value"] for item in web_task["containerDefinitions"][0]["environment"]
            }
            worker_environment = {
                item["name"]: item["value"] for item in worker_task["containerDefinitions"][0]["environment"]
            }
            self.assertEqual(web_environment["BACKGROUND_JOBS_ENABLED"], "false")
            self.assertEqual(web_environment["CSP_REPORT_ONLY"], "false")
            self.assertEqual(worker_environment["BACKGROUND_JOBS_ENABLED"], "true")

    def test_legacy_queue_flag_still_enables_worker_rendering(self) -> None:
        environment = self.deployment_environment()
        environment.pop("BACKGROUND_WORKER_ENABLED")
        with tempfile.TemporaryDirectory() as temporary_directory:
            worker_output = Path(temporary_directory) / "worker.json"
            with patch.dict(os.environ, environment, clear=True):
                runtime_environment = renderer.required_runtime_environment()
                renderer.render_worker(
                    REPOSITORY_ROOT / "aws/worker-task-definition.json",
                    worker_output,
                    runtime_environment,
                )
            self.assertTrue(worker_output.exists())

    def test_worker_defaults_off_and_removes_a_stale_render(self) -> None:
        environment = self.deployment_environment()
        environment.pop("BACKGROUND_JOBS_ENABLED")
        environment.pop("BACKGROUND_WORKER_ENABLED")
        with tempfile.TemporaryDirectory() as temporary_directory:
            worker_output = Path(temporary_directory) / "worker.json"
            worker_output.write_text('{"stale": true}\\n', encoding="utf-8")
            with patch.dict(os.environ, environment, clear=True):
                runtime_environment = renderer.required_runtime_environment()
                renderer.render_worker(
                    REPOSITORY_ROOT / "aws/worker-task-definition.json",
                    worker_output,
                    runtime_environment,
                )
            self.assertFalse(worker_output.exists())

    def test_empty_required_runtime_value_is_rejected(self) -> None:
        environment = self.deployment_environment()
        environment["AWS_STORAGE_BUCKET_NAME"] = ""
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(SystemExit, "AWS_STORAGE_BUCKET_NAME"):
                renderer.required_runtime_environment()

    def test_csp_report_only_defaults_safe_and_rejects_invalid_values(self) -> None:
        environment = self.deployment_environment()
        environment.pop("CSP_REPORT_ONLY")
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            with patch.dict(os.environ, environment, clear=True):
                runtime_environment = renderer.required_runtime_environment()
                renderer.render_web(
                    REPOSITORY_ROOT / "aws/task-definition.json",
                    output_directory / "web.json",
                    output_directory / "one-off.json",
                    runtime_environment,
                )
            task_definition = json.loads((output_directory / "web.json").read_text(encoding="utf-8"))
            rendered_environment = {
                item["name"]: item["value"] for item in task_definition["containerDefinitions"][0]["environment"]
            }
            self.assertEqual(rendered_environment["CSP_REPORT_ONLY"], "true")

        environment["CSP_REPORT_ONLY"] = "sometimes"
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.dict(os.environ, environment, clear=True):
                runtime_environment = renderer.required_runtime_environment()
                with self.assertRaisesRegex(SystemExit, "CSP_REPORT_ONLY"):
                    renderer.render_web(
                        REPOSITORY_ROOT / "aws/task-definition.json",
                        Path(temporary_directory) / "web.json",
                        Path(temporary_directory) / "one-off.json",
                        runtime_environment,
                    )


if __name__ == "__main__":
    unittest.main()
