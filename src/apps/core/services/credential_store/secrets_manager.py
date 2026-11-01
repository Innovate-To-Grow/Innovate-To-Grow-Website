"""AWS Secrets Manager credential store, used in production through the ECS task role.

The task role may read, describe, add versions to and relabel only the secrets in aws/cicd/identity-stack.json; it
cannot create, delete, rotate or re-policy them. A write never moves ``AWSCURRENT`` (it always passes the staged
label), every read is pinned to a version id, and every response must name the expected secret and version.
"""

import logging
import re

import boto3
from botocore import exceptions as botocore_errors
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from .base import (
    CURRENT_STAGE,
    FOREIGN_REFERENCE,
    VERSION_CONFLICT,
    CredentialStoreError,
    SecretDescription,
    StoredVersion,
    TransientCredentialStoreError,
    parse_payload,
    secret_id_for,
    serialize_payload,
    staged_label,
    validate_version_id,
)

logger = logging.getLogger(__name__)

PUT_FAILED = "The credential could not be saved to the credential store."
READ_FAILED = "The credential could not be read from the credential store."
DESCRIBE_FAILED = "The credential store's versions could not be listed."
RELABEL_FAILED = "The credential store's current version could not be updated."
UNEXPECTED_RESPONSE = "The credential store returned an unexpected response."

_TRANSIENT_CODES = frozenset(
    {
        "InternalFailure",
        "InternalServiceError",
        "RequestTimeout",
        "RequestTimeoutException",
        "ServiceUnavailable",
        "ServiceUnavailableException",
        "Throttling",
        "ThrottlingException",
        "TooManyRequestsException",
    }
)
# Network failures, and the task role's credentials not being fetched in time from the ECS credentials endpoint
# (or instance metadata): a later attempt can succeed. A misconfigured credential (PartialCredentialsError) cannot.
_TRANSIENT_BOTOCORE_ERRORS = (
    botocore_errors.ConnectionError,
    botocore_errors.HTTPClientError,
    botocore_errors.CredentialRetrievalError,
    botocore_errors.MetadataRetrievalError,
    botocore_errors.NoCredentialsError,
)
# Re-using a token whose version holds different bytes fails; the stored version decides whether it is ours.
_VERSION_CONFLICT_CODES = frozenset({"ResourceExistsException", "InvalidRequestException"})


def _mapped_error(exc: Exception, message: str) -> CredentialStoreError:
    if isinstance(exc, ClientError):
        response = exc.response if isinstance(exc.response, dict) else {}
        code = str((response.get("Error") or {}).get("Code", ""))
        status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode", 0)
        transient = code in _TRANSIENT_CODES or (isinstance(status, int) and status >= 500)
    else:
        # Never str(exc): ParamValidationError and friends echo parameter values, SecretString included.
        code = type(exc).__name__
        transient = isinstance(exc, _TRANSIENT_BOTOCORE_ERRORS)
    return (TransientCredentialStoreError if transient else CredentialStoreError)(message, code=code)


class SecretsManagerStore:
    def __init__(self, client=None):
        self._client = client

    def _secrets_manager(self):
        if self._client is None:
            # A fresh session per store: boto3's default session is not safe to share across threads.
            self._client = boto3.session.Session().client(
                "secretsmanager",
                region_name=settings.CREDENTIAL_STORE_AWS_REGION,
                config=Config(
                    connect_timeout=settings.CREDENTIAL_STORE_CONNECT_TIMEOUT_SECONDS,
                    read_timeout=settings.CREDENTIAL_STORE_READ_TIMEOUT_SECONDS,
                    retries={"total_max_attempts": settings.CREDENTIAL_STORE_TOTAL_MAX_ATTEMPTS, "mode": "standard"},
                ),
            )
        return self._client

    @sensitive_variables()
    def _call(self, operation: str, failure: str, **params) -> dict:
        """One API call. Every failure becomes fixed text plus the error code, raised with no exception chain."""
        try:
            response = getattr(self._secrets_manager(), operation)(**params)
        except (BotoCoreError, ClientError) as exc:
            error = _mapped_error(exc, failure)
        else:
            return response if isinstance(response, dict) else {}
        raise error from None

    def _arn_matches(self, secret_id: str, arn) -> bool:
        region, account = settings.CREDENTIAL_STORE_AWS_REGION, settings.CREDENTIAL_STORE_AWS_ACCOUNT_ID
        # Secrets Manager appends "-" and six random characters to the secret name.
        pattern = re.escape(f"arn:aws:secretsmanager:{region}:{account}:secret:{secret_id}") + "-[A-Za-z0-9]{6}"
        return isinstance(arn, str) and bool(re.fullmatch(pattern, arn))

    @sensitive_variables()
    def put(self, name: str, payload: dict, *, version_token: str) -> StoredVersion:
        secret_id = secret_id_for(name)
        secret_string = serialize_payload(payload)
        validate_version_id(version_token)
        conflict = None
        try:
            response = self._call(
                "put_secret_value",
                PUT_FAILED,
                SecretId=secret_id,
                ClientRequestToken=version_token,
                SecretString=secret_string,
                VersionStages=[staged_label()],
            )
        except CredentialStoreError as error:
            if error.code not in _VERSION_CONFLICT_CODES:
                raise
            conflict = error
        if conflict is not None:
            return self._existing_version(name, secret_string, version_token, conflict)
        if not self._arn_matches(secret_id, response.get("ARN")) or response.get("VersionId") != version_token:
            raise CredentialStoreError(UNEXPECTED_RESPONSE)
        return StoredVersion(arn=response["ARN"], version_id=version_token)

    @sensitive_variables()
    def _existing_version(self, name, secret_string, version_token, conflict) -> StoredVersion:
        try:
            arn = self.describe(name).arn
            stored = self.read(name, arn=arn, version_id=version_token)
        except CredentialStoreError:
            stored = None
        if stored is None:
            raise conflict
        if serialize_payload(stored) != secret_string:
            raise CredentialStoreError(VERSION_CONFLICT)
        return StoredVersion(arn=arn, version_id=version_token)

    @sensitive_variables()
    def read(self, name: str, *, arn: str, version_id: str) -> dict:
        secret_id = secret_id_for(name)
        if not self._arn_matches(secret_id, arn):
            raise CredentialStoreError(FOREIGN_REFERENCE)
        validate_version_id(version_id)
        response = self._call("get_secret_value", READ_FAILED, SecretId=arn, VersionId=version_id)
        if response.get("ARN") != arn or response.get("VersionId") != version_id:
            raise CredentialStoreError(UNEXPECTED_RESPONSE)
        return parse_payload(response.get("SecretString"))

    def describe(self, name: str) -> SecretDescription:
        secret_id = secret_id_for(name)
        response = self._call("describe_secret", DESCRIBE_FAILED, SecretId=secret_id)
        stages = response.get("VersionIdsToStages") or {}
        if not self._arn_matches(secret_id, response.get("ARN")) or not isinstance(stages, dict):
            raise CredentialStoreError(UNEXPECTED_RESPONSE)
        labelled = tuple(
            (str(version), tuple(str(label) for label in labels))
            for version, labels in sorted(stages.items())
            if isinstance(labels, list) and labels
        )
        return SecretDescription(arn=response["ARN"], version_stages=labelled)

    def move_current(self, name: str, version_id: str) -> bool:
        """Best effort: label ``version_id`` as current. A provider failure is logged and returns False."""
        secret_id_for(name)
        validate_version_id(version_id)
        try:
            description = self.describe(name)
            holder = description.current_version_id
            if holder != version_id:
                params = {"RemoveFromVersionId": holder} if holder else {}
                self._call(
                    "update_secret_version_stage",
                    RELABEL_FAILED,
                    SecretId=description.arn,
                    VersionStage=CURRENT_STAGE,
                    MoveToVersionId=version_id,
                    **params,
                )
        except CredentialStoreError as error:
            logger.warning("Credential store label update failed for %s (%s).", name, error.code or "no code")
            return False
        return True
