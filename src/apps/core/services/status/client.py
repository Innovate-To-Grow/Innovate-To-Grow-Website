"""Client facade for the status stack's IAM-protected internal endpoint.

Infrastructure credentials deliberately come from boto3's ambient credential
chain (the ECS task role in production).  The database-backed AWS credential
record is intended for application services such as SES and Bedrock and must
not be reused for operational access.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import OpenerDirector

import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError, PartialCredentialsError
from django.conf import settings

from .errors import PUBLIC_ERROR_MESSAGES, StatusFetchError
from .schema import (
    EXPECTED_SCHEMA_VERSION,
    MAX_COLLECTION_ITEMS,
    MAX_JSON_DEPTH,
    MAX_STRING_LENGTH,
    validate_status_payload,
)
from .transport import (
    EXPECTED_INTERNAL_PATH,
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT_SECONDS,
    default_opener_factory,
    fetch_status_payload,
    http_error_reason,
)

logger = logging.getLogger(__name__)

__all__ = [
    "EXPECTED_INTERNAL_PATH",
    "EXPECTED_SCHEMA_VERSION",
    "InternalStatusApiClient",
    "MAX_COLLECTION_ITEMS",
    "MAX_JSON_DEPTH",
    "MAX_RESPONSE_BYTES",
    "MAX_STRING_LENGTH",
    "PUBLIC_ERROR_MESSAGES",
    "REQUEST_TIMEOUT_SECONDS",
    "StatusFetchError",
    "validate_status_payload",
]


class InternalStatusApiClient:
    """Fetch and validate one live infrastructure payload from API Gateway."""

    def __init__(
        self,
        *,
        url: str | None = None,
        region: str | None = None,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
        session_factory: Callable[..., Any] | None = None,
        opener_factory: Callable[[], OpenerDirector] | None = None,
    ):
        self.region = (
            region or getattr(settings, "STATUS_API_REGION", "") or getattr(settings, "AWS_REGION", "") or "us-west-2"
        ).strip()
        self.url = (url if url is not None else getattr(settings, "STATUS_INTERNAL_API_URL", "")).strip()
        self.timeout = timeout
        self._session_factory = session_factory or boto3.Session
        self._opener_factory = opener_factory or default_opener_factory

    def fetch(self) -> dict[str, Any]:
        """Return a validated schema-v1 payload or raise ``StatusFetchError``."""

        try:
            payload = fetch_status_payload(
                url=self.url,
                region=self.region,
                timeout=self.timeout,
                session_factory=self._session_factory,
                opener_factory=self._opener_factory,
            )
        except StatusFetchError:
            raise
        except HTTPError as exc:
            reason = http_error_reason(exc.code)
            logger.warning("Internal status API request failed (reason=%s, status=%s)", reason, exc.code)
            raise StatusFetchError(reason) from None
        except TimeoutError:
            logger.warning("Internal status API request timed out")
            raise StatusFetchError("timeout") from None
        except URLError as exc:
            reason = "timeout" if isinstance(exc.reason, TimeoutError) else "upstream"
            logger.warning("Internal status API transport failed (reason=%s)", reason)
            raise StatusFetchError(reason) from None
        except (NoCredentialsError, PartialCredentialsError):
            logger.warning("Ambient AWS credentials are unavailable for the internal status API")
            raise StatusFetchError("credentials") from None
        except BotoCoreError:
            logger.warning("AWS request signing failed for the internal status API")
            raise StatusFetchError("credentials") from None
        except Exception:  # noqa: BLE001 -- admin dashboards must degrade instead of returning HTTP 500.
            # Transport exceptions may include signed headers or upstream
            # details, so log only the sanitized failure category.
            logger.error("Unexpected internal status API failure")
            raise StatusFetchError("error") from None

        validate_status_payload(payload)
        return payload
