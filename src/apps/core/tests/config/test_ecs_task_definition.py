import copy
import importlib.util
import json
import re
from pathlib import Path

from django.test import SimpleTestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
TASK_DEFINITION_PATH = REPOSITORY_ROOT / "aws" / "task-definition.json"
VALIDATOR_PATH = REPOSITORY_ROOT / "aws" / "validate_backend_task_definition.py"
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "deploy-backend.yml"

spec = importlib.util.spec_from_file_location("validate_backend_task_definition", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(validator)


class ECSTaskDefinitionTopologyTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.taskdef = json.loads(TASK_DEFINITION_PATH.read_text(encoding="utf-8"))

    def test_checked_in_template_has_safe_worker_topology(self):
        validator.validate_task_definition(self.taskdef, rendered=False)

    def test_validator_rejects_worker_running_the_web_entrypoint(self):
        taskdef = copy.deepcopy(self.taskdef)
        worker = next(
            container
            for container in taskdef["containerDefinitions"]
            if container["name"] == validator.WORKER_CONTAINER
        )
        worker.pop("entryPoint")

        with self.assertRaisesRegex(
            validator.TaskDefinitionValidationError,
            "override the image's Web/migration entrypoint",
        ):
            validator.validate_task_definition(taskdef, rendered=False)

    def test_validator_rejects_a_worker_port(self):
        taskdef = copy.deepcopy(self.taskdef)
        worker = next(
            container
            for container in taskdef["containerDefinitions"]
            if container["name"] == validator.WORKER_CONTAINER
        )
        worker["portMappings"] = [{"containerPort": 8001, "protocol": "tcp"}]

        with self.assertRaisesRegex(
            validator.TaskDefinitionValidationError,
            "must not expose a network port",
        ):
            validator.validate_task_definition(taskdef, rendered=False)

    def test_validator_rejects_a_non_deployment_revision_in_the_template(self):
        taskdef = copy.deepcopy(self.taskdef)
        web = next(
            container for container in taskdef["containerDefinitions"] if container["name"] == validator.WEB_CONTAINER
        )
        revision = next(item for item in web["environment"] if item["name"] == "AMPLIFY_CONFIG_REVISION")
        revision["value"] = "latest"

        with self.assertRaisesRegex(
            validator.TaskDefinitionValidationError,
            "must retain its deployment placeholder",
        ):
            validator.validate_task_definition(taskdef, rendered=False)

    def _rendered(self, **env_overrides):
        """Fill every template placeholder the way ``deploy-backend.yml`` does (worker mirrors Web)."""
        taskdef = copy.deepcopy(self.taskdef)
        web = next(c for c in taskdef["containerDefinitions"] if c["name"] == validator.WEB_CONTAINER)
        worker = next(c for c in taskdef["containerDefinitions"] if c["name"] == validator.WORKER_CONTAINER)
        values = {
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "AMPLIFY_CONFIG_REVISION": "1.1",
            "LEGACY_VIEW_ENABLED": "false",
            "LEGACY_ORIGIN_URL": "",
            "LEGACY_VIEWER_URL": "",
            "LEGACY_ORIGIN_HEADER_NAME": "",
        }
        for item in web["environment"]:
            item["value"] = env_overrides.get(item["name"], values.get(item["name"], "1"))
        for item in web["secrets"]:
            item["valueFrom"] = "arn:aws:secretsmanager:us-west-2:000000000000:secret:test"
        worker["environment"] = copy.deepcopy(web["environment"])
        worker["secrets"] = [
            copy.deepcopy(item) for item in web["secrets"] if item["name"] not in validator.WEB_ONLY_SECRETS
        ]
        return json.loads(re.sub(r"__[A-Z0-9_]+__", "x", json.dumps(taskdef)))

    def test_rendered_task_definition_with_trusted_proxy_hops_is_valid(self):
        validator.validate_task_definition(self._rendered(NUM_PROXIES="2"), rendered=True)

    def test_validator_rejects_a_rendered_task_without_a_positive_num_proxies(self):
        for value in ("0", "", "-1", "one", "1.5"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(validator.TaskDefinitionValidationError, "NUM_PROXIES must be a positive"):
                    validator.validate_task_definition(self._rendered(NUM_PROXIES=value), rendered=True)

    def test_validator_rejects_a_template_missing_num_proxies(self):
        taskdef = copy.deepcopy(self.taskdef)
        web = next(c for c in taskdef["containerDefinitions"] if c["name"] == validator.WEB_CONTAINER)
        web["environment"] = [item for item in web["environment"] if item["name"] != "NUM_PROXIES"]

        with self.assertRaisesRegex(validator.TaskDefinitionValidationError, "missing required shared environment"):
            validator.validate_task_definition(taskdef, rendered=False)

    def test_backend_workflow_renders_num_proxies_defaulting_to_one_alb_hop(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("NUM_PROXIES: ${{ vars.NUM_PROXIES || '1' }}", workflow)
        self.assertIn('"__NUM_PROXIES__": env_value("NUM_PROXIES", "1")', workflow)

    def test_backend_workflow_renders_and_validates_the_worker(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn('containers["itg-background-worker"]', workflow)
        self.assertIn('worker_container["environment"] = deepcopy(web_container["environment"])', workflow)
        self.assertIn('WEB_ONLY_SECRETS = {"LEGACY_ORIGIN_HEADER_VALUE"}', workflow)
        self.assertIn('if item["name"] not in WEB_ONLY_SECRETS', workflow)
        self.assertIn(
            "AMPLIFY_CONFIG_REVISION: ${{ github.run_id }}.${{ github.run_attempt }}",
            workflow,
        )
        self.assertIn(
            '"__AMPLIFY_CONFIG_REVISION__": env_value("AMPLIFY_CONFIG_REVISION")',
            workflow,
        )
        self.assertIn(
            "python aws/validate_backend_task_definition.py rendered-task-definition.json --rendered",
            workflow,
        )

    def test_backend_workflow_keeps_the_legacy_viewer_off_outside_production(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("DEPLOY_TARGET: ${{ matrix.target }}", workflow)
        self.assertIn('if env_value("DEPLOY_TARGET").strip() != "prod":', workflow)
        self.assertIn('mapping["__LEGACY_VIEW_ENABLED__"] = "false"', workflow)
        self.assertIn('secret_mapping["__LEGACY_ORIGIN_HEADER_SECRET_ARN__"] = ""', workflow)


class ECSRenderedLegacyViewerTests(SimpleTestCase):
    """Rendered-task rules for the private Legacy viewer (docs/deployment/legacy-view.md)."""

    SECRET_ARN = "arn:aws:secretsmanager:us-west-2:123456789012:secret:itg/backend/legacy-view-origin-header"

    def _rendered(self, *, legacy_env=None, legacy_secret=True):
        template = TASK_DEFINITION_PATH.read_text(encoding="utf-8")
        taskdef = json.loads(validator.PLACEHOLDER_RE.sub("rendered", template))
        containers = {container["name"]: container for container in taskdef["containerDefinitions"]}
        web = containers[validator.WEB_CONTAINER]
        worker = containers[validator.WORKER_CONTAINER]
        overrides = {
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
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
