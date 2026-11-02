import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.deploy import migrate_ecs, publish_image


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.definition = json.loads((Path(__file__).resolve().parents[3] / "aws/task-definition.json").read_text())
        self.definition["family"] = "itg-backend"

    def test_migration_is_isolated_and_preserves_release_credentials(self):
        original = copy.deepcopy(self.definition)
        migration = migrate_ecs.migration_definition(self.definition)
        self.assertEqual(self.definition, original)
        self.assertEqual(len(migration["containerDefinitions"]), 1)
        container = migration["containerDefinitions"][0]
        self.assertNotIn("healthCheck", container)
        self.assertNotIn("portMappings", container)
        self.assertEqual(container["entryPoint"], ["python"])
        self.assertEqual(container["command"], ["manage.py", "migrate", "--noinput"])
        self.assertEqual(container["secrets"], original["containerDefinitions"][0]["secrets"])

    def test_failed_migration_and_existing_task_block_release(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as source:
            json.dump(self.definition, source)
            source.flush()
            for responses in (
                [{"taskArns": ["existing"]}],
                [
                    {"taskArns": []},
                    {"services": [{"networkConfiguration": {}}]},
                    {"taskDefinition": {"taskDefinitionArn": "migration:1"}},
                    {"tasks": [{"taskArn": "task:1"}]},
                    {"tasks": [{"lastStatus": "STOPPED", "containers": [{"exitCode": 1}]}]},
                ],
            ):
                with (
                    self.subTest(responses=responses),
                    patch.dict(os.environ, ECS_CLUSTER="cluster", ECS_SERVICE="service"),
                    patch("sys.argv", ["migrate_ecs.py", source.name]),
                    patch.object(migrate_ecs, "aws", side_effect=responses),
                ):
                    with self.assertRaises(RuntimeError):
                        migrate_ecs.main()


class PublishTests(unittest.TestCase):
    def test_denied_image_lookup_is_not_treated_as_a_missing_image(self):
        denied = subprocess.CompletedProcess([], 255, "", "(AccessDeniedException)")
        with patch.object(publish_image.subprocess, "run", return_value=denied):
            with self.assertRaises(RuntimeError):
                publish_image.existing_digest("repo", "tag")

    def test_retry_reuses_existing_commit_without_docker_build_or_push(self):
        digest = "sha256:" + "a" * 64
        with (
            patch(
                "sys.argv",
                [
                    "publish",
                    "--repository",
                    "repo",
                    "--registry",
                    "registry",
                    "--tag",
                    "b" * 40,
                    "--context",
                    "archive/page",
                ],
            ),
            patch.object(publish_image, "existing_digest", return_value=digest),
            patch.object(publish_image.subprocess, "run") as docker,
        ):
            publish_image.main()
            docker.assert_not_called()
