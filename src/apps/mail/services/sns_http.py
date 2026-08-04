"""Bounded HTTPS transport for AWS SNS-controlled URLs."""

import ssl
from http.client import HTTPSConnection
from urllib.parse import urlsplit

from apps.core.utils.security import validate_aws_sns_https_url

DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024


class SnsHttpError(RuntimeError):
    """Raised when a validated SNS HTTPS request cannot be accepted safely."""


def fetch_sns_https(url: str, *, timeout: float = 5, max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES) -> bytes:
    """Fetch a small AWS SNS HTTPS resource without redirects or proxy routing.

    The strict hostname validator prevents arbitrary destinations. Using
    ``HTTPSConnection`` directly also avoids ambient proxy configuration and
    does not follow redirects, so an AWS response cannot redirect the request
    to a second, unvalidated location.
    """

    validated_url = validate_aws_sns_https_url(url)
    parsed = urlsplit(validated_url)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"

    tls_context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = HTTPSConnection(parsed.hostname, port=443, timeout=timeout, context=tls_context)
    try:
        connection.request("GET", target, headers={"Accept": "*/*", "User-Agent": "i2g-sns-client/1"})
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise SnsHttpError(f"SNS endpoint returned HTTP {response.status}")
        payload = response.read(max_bytes + 1)
    finally:
        connection.close()

    if len(payload) > max_bytes:
        raise SnsHttpError(f"SNS response exceeds the {max_bytes}-byte limit")
    return payload
