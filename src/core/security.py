"""Small security helpers shared across backend integrations."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_SNS_HOST_RE = re.compile(r"^sns(?:[.-][a-z0-9-]+)*\.amazonaws\.com(?:\.cn)?$")


class SecurityValidationError(ValueError):
    """Raised when untrusted input fails a security boundary check."""


def validate_aws_sns_https_url(url: str) -> str:
    """Return *url* only when it is an HTTPS URL hosted by AWS SNS."""
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise SecurityValidationError("SNS URL must be https")
    if parsed.username or parsed.password:
        raise SecurityValidationError("SNS URL must not include credentials")
    if parsed.port not in (None, 443):
        raise SecurityValidationError("SNS URL must use the default HTTPS port")
    if not _SNS_HOST_RE.fullmatch(host):
        raise SecurityValidationError("SNS URL host is not allowed")
    return url
