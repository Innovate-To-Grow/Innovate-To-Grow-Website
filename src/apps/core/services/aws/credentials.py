"""Shared AWS credential resolution for services that reuse the same IAM user."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings

from .secret_store import read_credentials


@dataclass(frozen=True)
class AwsCredentials:
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    region: str


class AwsCredentialsError(RuntimeError):
    """Raised when no AWS credentials are configured."""


def aws_credentials_available() -> bool:
    """Return True when shared AWS credentials can be resolved."""
    try:
        resolve_aws_credentials()
    except AwsCredentialsError:
        return False
    return True


def resolve_aws_credentials(service: str = "default", *, config=None) -> AwsCredentials:
    """Resolve AWS credentials from the active AWSCredentialConfig.

    The ``service`` argument is kept for call-site readability (SES, SNS,
    Bedrock) but all services share the same region.
    """
    from apps.core.models import AWSCredentialConfig

    aws = config if config is not None else AWSCredentialConfig.load()
    if not aws.is_configured:
        raise AwsCredentialsError("AWS credentials are not configured.")

    if getattr(aws, "credentials_secret_arn", ""):
        try:
            access_key, secret_key = read_credentials(aws.credentials_secret_arn)
        except Exception:
            raise AwsCredentialsError("AWS credentials could not be read from Secrets Manager.") from None
    elif getattr(settings, "AWS_CREDENTIALS_REQUIRE_SECRETS_MANAGER", False):
        raise AwsCredentialsError("Production AWS credentials must use Secrets Manager.")
    else:
        access_key, secret_key = aws.access_key_id, aws.secret_access_key
    return AwsCredentials(access_key_id=access_key, secret_access_key=secret_key, region=aws.region)
