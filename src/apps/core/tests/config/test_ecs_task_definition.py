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
        values = {"DJANGO_SETTINGS_MODULE": "config.settings.production", "AMPLIFY_CONFIG_REVISION": "1.1"}
        for item in web["environment"]:
            item["value"] = env_overrides.get(item["name"], values.get(item["name"], "1"))
        for item in web["secrets"]:
            item["valueFrom"] = "arn:aws:secretsmanager:us-west-2:000000000000:secret:test"
        worker["environment"] = copy.deepcopy(web["environment"])
        worker["secrets"] = copy.deepcopy(web["secrets"])
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
        self.assertIn('worker_container["secrets"] = deepcopy(web_container["secrets"])', workflow)
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
