"""Shared fixtures for the Amplify redirect tests."""

from botocore.exceptions import ClientError

from apps.cms.services.amplify import (
    canonical_amplify_base_rules,
)


def _client_error(code: str, status_code: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "provider detail must not leak"},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        },
        "UpdateApp",
    )


def _base_rules(*, proxy_admin_paths: bool = False):
    return canonical_amplify_base_rules(
        backend_proxy_url="https://api.example",
        proxy_admin_paths=proxy_admin_paths,
    )
