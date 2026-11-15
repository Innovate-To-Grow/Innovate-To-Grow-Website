import copy
import json

from django.test import SimpleTestCase

from apps.core.tests.project.config.production.test_ecs_task_definition import TASK_DEFINITION_PATH, validator


class ECSRenderedLegacyViewerTests(SimpleTestCase):
    """Rendered-task rules for the private Legacy viewer (docs/operations/legacy-view.md)."""

    SECRET_ARN = "arn:aws:secretsmanager:us-west-2:123456789012:secret:itg/backend/legacy-view-origin-header"

    def _rendered(self, *, legacy_env=None, legacy_secret=True):
        template = TASK_DEFINITION_PATH.read_text(encoding="utf-8")
        taskdef = json.loads(validator.PLACEHOLDER_RE.sub("rendered", template))
        containers = {container["name"]: container for container in taskdef["containerDefinitions"]}
        web = containers[validator.WEB_CONTAINER]
        worker = containers[validator.WORKER_CONTAINER]
        overrides = {
            "DJANGO_SETTINGS_MODULE": "config.settings.environments.production",
            "AMPLIFY_CONFIG_REVISION": "1.1",
            "NUM_PROXIES": "1",
            "LEGACY_VIEW_ENABLED": "false",
            "LEGACY_ORIGIN_URL": "",
            "LEGACY_VIEWER_URL": "",
            "LEGACY_ORIGIN_HEADER_NAME": "",
            "LEGACY_CONNECT_TIMEOUT_SECONDS": "3",
            "LEGACY_READ_TIMEOUT_SECONDS": "15",
            **(legacy_env or {}),
        }
        for item in web["environment"]:
            item["value"] = overrides.get(item["name"], "rendered")
        web["secrets"] = [
            {**item, "valueFrom": f"arn:aws:secretsmanager:us-west-2:123456789012:secret:{item['name']}"}
            for item in web["secrets"]
            if legacy_secret or item["name"] != "LEGACY_ORIGIN_HEADER_VALUE"
        ]
        worker["environment"] = copy.deepcopy(web["environment"])
        worker["secrets"] = [
            copy.deepcopy(item) for item in web["secrets"] if item["name"] not in validator.WEB_ONLY_SECRETS
        ]
        return taskdef, web, worker

    def _enabled_env(self, **overrides):
        return {
            "LEGACY_VIEW_ENABLED": "true",
            "LEGACY_ORIGIN_URL": "http://172.31.69.63:8080",
            "LEGACY_VIEWER_URL": "https://d111111abcdef8.cloudfront.net",
            "LEGACY_ORIGIN_HEADER_NAME": "X-I2G-Legacy-Origin-Secret",
            **overrides,
        }

    def test_disabled_and_enabled_renders_are_valid(self):
        validator.validate_task_definition(self._rendered(legacy_secret=False)[0], rendered=True)
        validator.validate_task_definition(self._rendered(legacy_env=self._enabled_env())[0], rendered=True)

    def test_worker_must_not_receive_the_origin_header_secret(self):
        taskdef, web, worker = self._rendered()
        worker["secrets"] = copy.deepcopy(web["secrets"])

        with self.assertRaisesRegex(validator.TaskDefinitionValidationError, "must not receive Web-only secrets"):
            validator.validate_task_definition(taskdef, rendered=True)

    def test_origin_header_value_cannot_be_a_literal_environment_value(self):
        taskdef, web, worker = self._rendered()
        for container in (web, worker):
            container["environment"].append({"name": "LEGACY_ORIGIN_HEADER_VALUE", "value": "x" * 40})

        with self.assertRaisesRegex(validator.TaskDefinitionValidationError, "never a literal environment value"):
            validator.validate_task_definition(taskdef, rendered=True)

    def test_enabled_viewer_requires_the_origin_header_secret(self):
        taskdef = self._rendered(legacy_env=self._enabled_env(), legacy_secret=False)[0]

        with self.assertRaisesRegex(validator.TaskDefinitionValidationError, "requires its origin URL"):
            validator.validate_task_definition(taskdef, rendered=True)

    def test_rejects_unsafe_legacy_settings(self):
        cases = {
            "LEGACY_ORIGIN_URL must be a private": {"LEGACY_ORIGIN_URL": "http://8.8.8.8:8080"},
            "LEGACY_VIEWER_URL must be an HTTPS": {"LEGACY_VIEWER_URL": "https://viewer.example.com"},
            "LEGACY_READ_TIMEOUT_SECONDS must be between": {"LEGACY_READ_TIMEOUT_SECONDS": "600"},
            "LEGACY_CONNECT_TIMEOUT_SECONDS must be between": {"LEGACY_CONNECT_TIMEOUT_SECONDS": "soon"},
            "LEGACY_ORIGIN_HEADER_NAME is not a valid": {"LEGACY_ORIGIN_HEADER_NAME": "Bad Header"},
        }
        for message, override in cases.items():
            with self.subTest(message=message):
                taskdef = self._rendered(legacy_env=self._enabled_env(**override))[0]
                with self.assertRaisesRegex(validator.TaskDefinitionValidationError, message):
                    validator.validate_task_definition(taskdef, rendered=True)
