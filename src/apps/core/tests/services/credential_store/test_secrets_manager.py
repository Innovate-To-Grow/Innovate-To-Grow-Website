"""The Secrets Manager store against botocore's Stubber: exact parameters, pinned reads, and error mapping."""

import json
from unittest.mock import Mock, patch

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import (
    CredentialRetrievalError,
    EndpointConnectionError,
    MetadataRetrievalError,
    NoCredentialsError,
    ParamValidationError,
    PartialCredentialsError,
    ReadTimeoutError,
)
from botocore.stub import Stubber
from django.test import SimpleTestCase, override_settings

from apps.core.services.credential_store import (
    CredentialStoreError,
    TransientCredentialStoreError,
    get_store,
    version_token_for,
)
from apps.core.services.credential_store.secrets_manager import PUT_FAILED, SecretsManagerStore

NAME = "microsoft_graph_certificate_key"
SECRET_ID = "itg/backend/microsoft-graph/certificate-key"
ARN = f"arn:aws:secretsmanager:us-west-2:394167325273:secret:{SECRET_ID}-AbC123"
MARKER = "do-not-echo-" + "k" * 40
PAYLOAD = {"schema": "test/1", "private_key_pem": MARKER, "public_key_sha256": "a" * 64}
CANONICAL = json.dumps(PAYLOAD, sort_keys=True, separators=(",", ":"))
TOKEN = version_token_for(NAME, "a" * 64)
OLD_TOKEN = version_token_for(NAME, "b" * 64)


class SecretsManagerStoreTests(SimpleTestCase):
    def setUp(self):
        # Unsigned: the stubber answers before any request would be signed or sent.
        client = boto3.session.Session().client(
            "secretsmanager", region_name="us-west-2", config=Config(signature_version=UNSIGNED)
        )
        self.stubber = Stubber(client)
        self.stubber.activate()
        self.addCleanup(self.stubber.deactivate)
        self.store = SecretsManagerStore(client=client)

    def tearDown(self):
        self.stubber.assert_no_pending_responses()

    def assert_clean_error(self, error):
        self.assertNotIn(MARKER, str(error))
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)

    def expect_get(self, version_id=TOKEN, *, secret_string=CANONICAL, response_version=None):
        self.stubber.add_response(
            "get_secret_value",
            {"ARN": ARN, "Name": SECRET_ID, "VersionId": response_version or version_id, "SecretString": secret_string},
            {"SecretId": ARN, "VersionId": version_id},
        )

    def expect_describe(self, stages):
        self.stubber.add_response(
            "describe_secret", {"ARN": ARN, "Name": SECRET_ID, "VersionIdsToStages": stages}, {"SecretId": SECRET_ID}
        )

    def test_put_sends_the_token_and_staged_label_so_current_never_moves(self):
        self.stubber.add_response(
            "put_secret_value",
            {"ARN": ARN, "Name": SECRET_ID, "VersionId": TOKEN, "VersionStages": ["I2G-STAGED"]},
            {
                "SecretId": SECRET_ID,
                "ClientRequestToken": TOKEN,
                "SecretString": CANONICAL,
                "VersionStages": ["I2G-STAGED"],
            },
        )
        stored = self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.assertEqual((stored.arn, stored.version_id), (ARN, TOKEN))

    def test_put_refuses_a_response_for_another_secret_or_version(self):
        for response in (
            {"ARN": ARN.replace("certificate-key", "other"), "VersionId": TOKEN},
            {"ARN": ARN, "VersionId": OLD_TOKEN},
        ):
            with self.subTest(response=response):
                self.stubber.add_response("put_secret_value", response)
                with self.assertRaisesMessage(CredentialStoreError, "unexpected response"):
                    self.store.put(NAME, PAYLOAD, version_token=TOKEN)

    def test_reused_token_is_accepted_only_when_the_stored_version_is_identical(self):
        self.stubber.add_client_error("put_secret_value", "ResourceExistsException", "exists", 400)
        self.expect_describe({TOKEN: ["I2G-STAGED"]})
        self.expect_get()
        self.assertEqual(self.store.put(NAME, PAYLOAD, version_token=TOKEN).version_id, TOKEN)

        self.stubber.add_client_error("put_secret_value", "ResourceExistsException", "exists", 400)
        self.expect_describe({TOKEN: ["I2G-STAGED"]})
        self.expect_get(secret_string=json.dumps({**PAYLOAD, "public_key_sha256": "c" * 64}))
        with self.assertRaisesMessage(CredentialStoreError, "different value") as conflict:
            self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.assert_clean_error(conflict.exception)

    def test_reused_token_that_cannot_be_checked_reports_the_original_failure(self):
        self.stubber.add_client_error("put_secret_value", "InvalidRequestException", "scheduled for deletion", 400)
        self.stubber.add_client_error("describe_secret", "InvalidRequestException", "scheduled for deletion", 400)
        with self.assertRaises(CredentialStoreError) as failure:
            self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.assertEqual(failure.exception.code, "InvalidRequestException")
        self.assertIn(PUT_FAILED, str(failure.exception))

    def test_read_always_names_the_pinned_version_and_checks_the_answer(self):
        self.expect_get()
        self.assertEqual(self.store.read(NAME, arn=ARN, version_id=TOKEN), PAYLOAD)
        self.expect_get(response_version=OLD_TOKEN)
        with self.assertRaisesMessage(CredentialStoreError, "unexpected response"):
            self.store.read(NAME, arn=ARN, version_id=TOKEN)
        self.expect_get(secret_string="[1, 2]")
        with self.assertRaisesMessage(CredentialStoreError, "not a JSON object"):
            self.store.read(NAME, arn=ARN, version_id=TOKEN)

    def test_foreign_arns_are_refused_before_any_call(self):
        for arn in (
            ARN.replace("394167325273", "111111111111"),
            ARN.replace("us-west-2", "us-east-1"),
            ARN.replace("certificate-key-AbC123", "certificate-key-extra-AbC123"),
            "arn:aws:secretsmanager:us-west-2:394167325273:secret:itg/backend/aws-credentials/1-AbC123",
            SECRET_ID,
        ):
            with self.subTest(arn=arn), self.assertRaisesMessage(CredentialStoreError, "does not belong"):
                self.store.read(NAME, arn=arn, version_id=TOKEN)
        with self.assertRaises(CredentialStoreError):
            self.store.put("gmail_service_account_key", PAYLOAD, version_token=TOKEN)

    def test_provider_errors_map_to_permanent_or_transient_with_the_code_only(self):
        cases = (
            ("AccessDeniedException", 400, False),
            ("ResourceNotFoundException", 400, False),
            ("DecryptionFailure", 400, False),
            ("ThrottlingException", 400, True),
            ("InternalServiceError", 500, True),
            ("SomethingNew", 503, True),
        )
        for code, status, transient in cases:
            with self.subTest(code=code):
                self.stubber.add_client_error("get_secret_value", code, f"message with {MARKER}", status)
                with self.assertRaises(CredentialStoreError) as failure:
                    self.store.read(NAME, arn=ARN, version_id=TOKEN)
                self.assertEqual(failure.exception.code, code)
                self.assertEqual(failure.exception.transient, transient)
                self.assertEqual(isinstance(failure.exception, TransientCredentialStoreError), transient)
                self.assert_clean_error(failure.exception)

    def test_parameter_validation_errors_never_echo_the_secret_string(self):
        # Botocore validates parameters before sending, so an unstubbed client makes no request here.
        client = boto3.session.Session().client(
            "secretsmanager", region_name="us-west-2", config=Config(signature_version=UNSIGNED)
        )
        with self.assertRaises(ParamValidationError) as raw:
            client.put_secret_value(SecretId=SECRET_ID, ClientRequestToken=TOKEN, SecretString={"key": MARKER})
        self.assertIn(MARKER, str(raw.exception))  # botocore itself echoes the value

        with self.assertRaises(CredentialStoreError) as failure:
            SecretsManagerStore(client=client)._call(
                "put_secret_value",
                PUT_FAILED,
                SecretId=SECRET_ID,
                ClientRequestToken=TOKEN,
                SecretString={"key": MARKER},
            )
        self.assertEqual(failure.exception.code, "ParamValidationError")
        self.assertFalse(failure.exception.transient)
        self.assert_clean_error(failure.exception)

    def test_timeouts_connection_and_task_role_credential_failures_are_transient(self):
        # The ECS credentials endpoint failing or timing out for a moment must not fail queued email for good.
        for exc in (
            ReadTimeoutError(endpoint_url="https://example.invalid"),
            EndpointConnectionError(endpoint_url="x"),
            NoCredentialsError(),
            CredentialRetrievalError(provider="container-role", error_msg="timed out"),
            MetadataRetrievalError(error_msg="timed out"),
        ):
            with self.subTest(exc=type(exc).__name__):
                client = Mock()
                client.put_secret_value.side_effect = exc
                with self.assertRaises(TransientCredentialStoreError) as failure:
                    SecretsManagerStore(client=client).put(NAME, PAYLOAD, version_token=TOKEN)
                self.assertEqual(failure.exception.code, type(exc).__name__)
                self.assert_clean_error(failure.exception)

    def test_a_misconfigured_credential_is_permanent(self):
        client = Mock()
        client.put_secret_value.side_effect = PartialCredentialsError(provider="env", cred_var="AWS_SECRET_ACCESS_KEY")

        with self.assertRaises(CredentialStoreError) as failure:
            SecretsManagerStore(client=client).put(NAME, PAYLOAD, version_token=TOKEN)

        self.assertFalse(failure.exception.transient)
        self.assertEqual(failure.exception.code, "PartialCredentialsError")
        self.assert_clean_error(failure.exception)

    def test_move_current_relabels_from_the_holder_and_skips_when_already_current(self):
        self.expect_describe({OLD_TOKEN: ["AWSCURRENT"], TOKEN: ["I2G-STAGED"]})
        self.stubber.add_response(
            "update_secret_version_stage",
            {"ARN": ARN, "Name": SECRET_ID},
            {"SecretId": ARN, "VersionStage": "AWSCURRENT", "MoveToVersionId": TOKEN, "RemoveFromVersionId": OLD_TOKEN},
        )
        self.assertTrue(self.store.move_current(NAME, TOKEN))

        self.expect_describe({TOKEN: ["I2G-STAGED", "AWSCURRENT"]})
        self.assertTrue(self.store.move_current(NAME, TOKEN))

    def test_move_current_failure_is_logged_not_raised(self):
        self.expect_describe({OLD_TOKEN: ["AWSCURRENT"], TOKEN: ["I2G-STAGED"]})
        self.stubber.add_client_error("update_secret_version_stage", "AccessDeniedException", MARKER, 400)
        with self.assertLogs("apps.core.services.credential_store.secrets_manager", level="WARNING") as logs:
            self.assertFalse(self.store.move_current(NAME, TOKEN))
        self.assertIn("AccessDeniedException", logs.output[0])
        self.assertNotIn(MARKER, logs.output[0])

    def test_describe_reports_labels_and_the_current_version(self):
        self.expect_describe({TOKEN: ["AWSCURRENT"], OLD_TOKEN: ["AWSPREVIOUS"]})
        description = self.store.describe(NAME)
        self.assertEqual(description.arn, ARN)
        self.assertEqual(dict(description.version_stages), {TOKEN: ("AWSCURRENT",), OLD_TOKEN: ("AWSPREVIOUS",)})
        self.assertEqual(description.stages_of(OLD_TOKEN), ("AWSPREVIOUS",))
        self.assertEqual(description.current_version_id, TOKEN)


class SecretsManagerClientTests(SimpleTestCase):
    @override_settings(
        CREDENTIAL_STORE_AWS_REGION="us-west-2",
        CREDENTIAL_STORE_CONNECT_TIMEOUT_SECONDS=2,
        CREDENTIAL_STORE_READ_TIMEOUT_SECONDS=4,
        CREDENTIAL_STORE_TOTAL_MAX_ATTEMPTS=5,
    )
    def test_client_uses_the_configured_region_timeouts_and_retries(self):
        with patch("apps.core.services.credential_store.secrets_manager.boto3.session.Session") as session:
            SecretsManagerStore()._secrets_manager()
        args, kwargs = session.return_value.client.call_args
        self.assertEqual(args, ("secretsmanager",))
        self.assertEqual(kwargs["region_name"], "us-west-2")
        config = kwargs["config"]
        self.assertEqual((config.connect_timeout, config.read_timeout), (2, 4))
        self.assertEqual(config.retries, {"total_max_attempts": 5, "mode": "standard"})

    @override_settings(CREDENTIAL_STORE_BACKEND="secretsmanager", CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER=True)
    def test_production_selection_returns_the_secrets_manager_store(self):
        self.assertIsInstance(get_store(), SecretsManagerStore)
