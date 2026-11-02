import io
import json
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.core.models import AWSCredentialConfig
from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials
from apps.core.services.aws.secret_store import _read_credentials, read_credentials

ARN = "arn:aws:secretsmanager:us-west-2:394167325273:secret:itg/backend/aws-credentials/1-abc123"
KEYS = {"access_key_id": "test-key", "secret_access_key": "test-private-value"}


class SecretStoreTests(TestCase):
    def setUp(self):
        _read_credentials.cache_clear()
        self.addCleanup(_read_credentials.cache_clear)

    def test_cache_is_memory_only_and_expires_for_rotation(self):
        client = Mock()
        client.get_secret_value.return_value = {"SecretString": json.dumps(KEYS)}
        with (
            patch("apps.core.services.aws.secret_store.boto3.client", return_value=client),
            patch("apps.core.services.aws.secret_store.time.monotonic", side_effect=[120, 125, 181]),
        ):
            self.assertEqual(read_credentials(ARN), tuple(KEYS.values()))
            read_credentials(ARN)
            self.assertEqual(client.get_secret_value.call_count, 1)
            read_credentials(ARN)
            self.assertEqual(client.get_secret_value.call_count, 2)

    def test_outside_namespace_and_incomplete_secrets_are_rejected(self):
        with patch("apps.core.services.aws.secret_store.boto3.client") as factory:
            with self.assertRaises(ValueError):
                read_credentials(ARN.replace("itg/backend", "another/project"))
            factory.assert_not_called()
            factory.return_value.get_secret_value.return_value = {"SecretString": "{}"}
            with self.assertRaises(ValueError):
                read_credentials(ARN)

    @override_settings(AWS_CREDENTIALS_REQUIRE_SECRETS_MANAGER=True)
    def test_production_refuses_database_credentials_and_plaintext_writes(self):
        config = AWSCredentialConfig(**KEYS)
        self.assertFalse(config.is_configured)
        with self.assertRaises(AwsCredentialsError):
            resolve_aws_credentials(config=config)
        with self.assertRaises(ValidationError):
            config.save()

    @override_settings(AWS_CREDENTIALS_REQUIRE_SECRETS_MANAGER=True)
    def test_cloud_credentials_take_precedence_and_failure_never_falls_back(self):
        config = AWSCredentialConfig(credentials_secret_arn=ARN, **KEYS)
        with patch("apps.core.services.aws.credentials.read_credentials", return_value=("cloud-key", "cloud-private")):
            resolved = resolve_aws_credentials(config=config)
            self.assertEqual(resolved.access_key_id, "cloud-key")
            self.assertNotIn("cloud-private", repr(resolved))
        with patch("apps.core.services.aws.credentials.read_credentials", side_effect=ValueError("sensitive")):
            with self.assertRaisesMessage(AwsCredentialsError, "could not be read") as error:
                resolve_aws_credentials(config=config)
            self.assertNotIn("sensitive", str(error.exception))

    def test_model_rejects_cross_project_reference(self):
        with self.assertRaises(ValidationError):
            AWSCredentialConfig(credentials_secret_arn=ARN.replace("itg/backend", "releviz/prod")).save()

    @override_settings(AWS_CREDENTIALS_REQUIRE_SECRETS_MANAGER=True)
    def test_admin_reports_missing_reference_before_save(self):
        from apps.core.admin.service_credentials.aws import AWSCredentialConfigForm

        form = AWSCredentialConfigForm(data={"name": "Production", "is_active": True, "default_region": "us-west-2"})
        self.assertFalse(form.is_valid())
        self.assertIn("credentials_secret_arn", form.errors)

    @override_settings(AWS_CREDENTIALS_REQUIRE_SECRETS_MANAGER=True)
    def test_bedrock_and_agent_clients_use_cloud_keys(self):
        from apps.system_intelligence.services.agents.litellm import bedrock_litellm_credentials
        from apps.system_intelligence.services.bedrock.clients._aws import get_client

        config = AWSCredentialConfig(credentials_secret_arn=ARN)
        with (
            patch("apps.core.services.aws.credentials.read_credentials", return_value=("cloud-key", "cloud-private")),
            patch("apps.system_intelligence.services.bedrock.clients._aws.boto3.client") as factory,
        ):
            get_client(config)
            self.assertEqual(factory.call_args.kwargs["aws_secret_access_key"], "cloud-private")
            self.assertEqual(bedrock_litellm_credentials(config)["aws_access_key_id"], "cloud-key")


class CredentialMigrationTests(TestCase):
    def setUp(self):
        self.config = AWSCredentialConfig.objects.create(name="AWS", is_active=True, **KEYS)
        self.client = Mock()
        self.client.exceptions.ResourceExistsException = type("ResourceExists", (Exception,), {})
        self.client.create_secret.return_value = {"ARN": ARN}
        self.client.get_secret_value.return_value = {"ARN": ARN, "SecretString": json.dumps(KEYS)}
        self.patcher = patch(
            "apps.core.management.commands.migrate_aws_credentials.boto3.client", return_value=self.client
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def run_command(self, **kwargs):
        output = io.StringIO()
        call_command("migrate_aws_credentials", stdout=output, **kwargs)
        for value in KEYS.values():
            self.assertNotIn(value, output.getvalue())

    def test_copy_keeps_old_containers_working_until_explicit_clear(self):
        self.run_command()
        self.config.refresh_from_db()
        self.assertEqual(self.config.credentials_secret_arn, ARN)
        self.assertEqual(self.config.secret_access_key, KEYS["secret_access_key"])
        self.run_command(clear_legacy=True)
        self.config.refresh_from_db()
        self.assertEqual(self.config.access_key_id, "")
        self.assertEqual(self.config.secret_access_key, "")
        self.assertTrue(self.config.is_configured)
        self.run_command(clear_legacy=True)
        self.client.create_secret.assert_called_once()

    def test_mismatched_cloud_copy_never_erases_database_value(self):
        self.client.get_secret_value.return_value["SecretString"] = json.dumps(
            {**KEYS, "secret_access_key": "different"}
        )
        with self.assertRaises(CommandError):
            self.run_command()
        self.config.refresh_from_db()
        self.assertEqual(self.config.credentials_secret_arn, "")
        self.assertEqual(self.config.secret_access_key, KEYS["secret_access_key"])

    def test_clear_cannot_skip_copy_and_verification(self):
        with self.assertRaises(CommandError):
            self.run_command(clear_legacy=True)
        self.config.refresh_from_db()
        self.assertEqual(self.config.secret_access_key, KEYS["secret_access_key"])

    def test_retry_reuses_existing_secret_without_overwriting_it(self):
        self.client.create_secret.side_effect = self.client.exceptions.ResourceExistsException()
        self.run_command()
        self.config.refresh_from_db()
        self.assertEqual(self.config.credentials_secret_arn, ARN)
        self.client.put_secret_value.assert_not_called()
