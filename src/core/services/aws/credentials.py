"""Shared AWS credential resolution for services that reuse the same IAM user."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AwsCredentials:
    access_key_id: str
    secret_access_key: str
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


def resolve_aws_credentials() -> AwsCredentials:
    """Resolve AWS credentials from AWSCredentialConfig, falling back to SES keys."""
    from core.models import AWSCredentialConfig, EmailServiceConfig

    aws = AWSCredentialConfig.load()
    if aws.is_configured:
        return AwsCredentials(
            access_key_id=aws.access_key_id,
            secret_access_key=aws.secret_access_key,
            region=aws.default_region or "us-west-2",
        )

    email = EmailServiceConfig.load()
    if email.ses_configured:
        return AwsCredentials(
            access_key_id=email.ses_access_key_id,
            secret_access_key=email.ses_secret_access_key,
            region=email.ses_region or "us-west-2",
        )

    raise AwsCredentialsError("AWS credentials are not configured.")
