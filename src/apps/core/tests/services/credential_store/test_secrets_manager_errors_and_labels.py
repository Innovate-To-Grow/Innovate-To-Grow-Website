from unittest.mock import Mock

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

from apps.core.services.credential_store import (
    CredentialStoreError,
    TransientCredentialStoreError,
)
from apps.core.services.credential_store.secrets_manager import PUT_FAILED, SecretsManagerStore
from apps.core.tests.services.credential_store.test_secrets_manager import (
    ARN,
    MARKER,
    NAME,
    OLD_TOKEN,
    PAYLOAD,
    SECRET_ID,
    TOKEN,
    _SecretsManagerStoreCase,
)


class SecretsManagerStoreTests(_SecretsManagerStoreCase):
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
