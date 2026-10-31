"""Credential store settings per environment, and the system check that refuses a non-Secrets-Manager production."""

from unittest.mock import patch

from django.conf import settings
from django.core.checks import registry
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import SimpleTestCase, override_settings

from apps.core.checks import check_credential_store
from apps.core.services.credential_store import CredentialStoreError, get_store
from config.settings.base.framework.environment import BASE_DIR
from config.settings.base.integrations import credential_store as base_settings
from config.settings.environments import test as ci_settings

from .test_prod_cache import PROD_ENV, reload_prod_settings


def error_ids():
    return [error.id for error in check_credential_store()]


class CredentialStoreSettingsTests(SimpleTestCase):
    def test_base_defaults_keep_local_keys_in_the_ignored_data_directory(self):
        self.assertEqual(base_settings.CREDENTIAL_STORE_BACKEND, "local_file")
        self.assertFalse(base_settings.CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER)
        self.assertEqual(base_settings.CREDENTIAL_STORE_LOCAL_DIR.parent, BASE_DIR / "data")
        repository = BASE_DIR.parent
        self.assertIn("src/data/", (repository / ".gitignore").read_text().splitlines())
        self.assertIn("data/", (BASE_DIR / ".dockerignore").read_text().splitlines())

    def test_graph_key_secret_sits_outside_the_aws_credentials_namespace(self):
        secret_id = base_settings.CREDENTIAL_STORE_SECRETS["microsoft_graph_certificate_key"]
        self.assertEqual(secret_id, "itg/backend/microsoft-graph/certificate-key")
        self.assertFalse(secret_id.startswith("itg/backend/aws-credentials/"))

    def test_tests_use_the_memory_store(self):
        self.assertEqual(ci_settings.CREDENTIAL_STORE_BACKEND, "memory")
        self.assertEqual(settings.CREDENTIAL_STORE_BACKEND, "memory")

    def test_production_requires_secrets_manager_and_passes_its_own_check(self):
        with patch.dict("os.environ", PROD_ENV, clear=True):
            production = reload_prod_settings()
        self.assertEqual(production.CREDENTIAL_STORE_BACKEND, "secretsmanager")
        self.assertTrue(production.CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER)
        self.assertTrue(production.AWS_CREDENTIALS_REQUIRE_SECRETS_MANAGER)
        values = {name: getattr(production, name) for name in dir(production) if name.startswith("CREDENTIAL_STORE_")}
        with override_settings(**values):
            self.assertEqual(error_ids(), [])


class CredentialStoreCheckTests(SimpleTestCase):
    def test_check_is_registered(self):
        self.assertIn(check_credential_store, registry.registry.get_checks())

    def test_default_and_test_settings_pass(self):
        self.assertEqual(error_ids(), [])

    def test_require_flag_refuses_every_backend_but_secrets_manager(self):
        for backend in ("local_file", "memory"):
            with self.subTest(backend=backend):
                with override_settings(CREDENTIAL_STORE_BACKEND=backend, CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER=True):
                    self.assertEqual(error_ids(), ["core.E002"])
                    with self.assertRaisesMessage(CredentialStoreError, "only in AWS Secrets Manager"):
                        get_store()
        with override_settings(
            CREDENTIAL_STORE_BACKEND="secretsmanager", CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER=True
        ):
            self.assertEqual(error_ids(), [])

    @override_settings(CREDENTIAL_STORE_BACKEND="memory", CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER=True)
    def test_management_commands_stop_on_the_require_flag(self):
        with self.assertRaises(SystemCheckError):
            call_command("check")

    def test_unknown_backend_is_refused(self):
        with override_settings(CREDENTIAL_STORE_BACKEND="plaintext"):
            self.assertEqual(error_ids(), ["core.E001"])
            with self.assertRaisesMessage(CredentialStoreError, "names no credential store"):
                get_store()

    def test_secret_names_must_be_valid_and_outside_the_aws_credentials_namespace(self):
        for secrets in (
            {"graph": "itg/backend/aws-credentials/graph"},
            {"graph": "../graph"},
            {"graph": ""},
            {"graph": None},
            ["itg/backend/microsoft-graph/certificate-key"],
        ):
            with self.subTest(secrets=secrets), override_settings(CREDENTIAL_STORE_SECRETS=secrets):
                self.assertEqual(error_ids(), ["core.E003"])

    def test_staged_label_and_limits_are_validated(self):
        for label in ("AWSCURRENT", "awspending", "", "has space", None):
            with self.subTest(label=label), override_settings(CREDENTIAL_STORE_STAGED_LABEL=label):
                self.assertEqual(error_ids(), ["core.E004"])
        for value in (0, -1, True, "5", None):
            with self.subTest(value=value), override_settings(CREDENTIAL_STORE_READ_TIMEOUT_SECONDS=value):
                self.assertEqual(error_ids(), ["core.E005"])

    def test_graph_certificate_limits_are_positive_settings_checked_at_startup(self):
        self.assertEqual(
            (
                settings.GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS,
                settings.GRAPH_CERTIFICATE_MAX_INPUT_BYTES,
                settings.GRAPH_CERTIFICATE_CLOCK_SKEW_SECONDS,
                settings.GRAPH_CERTIFICATE_CHECK_TIMEOUT_SECONDS,
            ),
            (2048, 65536, 300, 10),
        )
        for name in (
            "GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS",
            "GRAPH_CERTIFICATE_MAX_INPUT_BYTES",
            "GRAPH_CERTIFICATE_CHECK_TIMEOUT_SECONDS",
        ):
            with self.subTest(name=name), override_settings(**{name: 0}):
                self.assertEqual(error_ids(), ["core.E005"])
        # No clock skew allowance at all is a valid choice.
        with override_settings(GRAPH_CERTIFICATE_CLOCK_SKEW_SECONDS=0):
            self.assertEqual(error_ids(), [])
