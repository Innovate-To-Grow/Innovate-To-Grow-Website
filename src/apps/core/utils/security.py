"""Small security helpers shared across backend integrations."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


class SecurityValidationError(ValueError):
    """Raised when untrusted input fails a security boundary check."""


def _is_safe_dns_label(label: str) -> bool:
    if not label or len(label) > 63 or label.startswith("-") or label.endswith("-"):
        return False
    return all(char.isascii() and (char.isalnum() or char == "-") for char in label)


def _is_allowed_sns_host(host: str) -> bool:
    for suffix in (".amazonaws.com", ".amazonaws.com.cn"):
        if host == f"sns{suffix}":
            return True
        if not host.endswith(suffix):
            continue
        labels = host[: -len(suffix)].split(".")
        return labels[0] == "sns" and all(_is_safe_dns_label(label) for label in labels[1:])
    return False


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
    if not _is_allowed_sns_host(host):
        raise SecurityValidationError("SNS URL host is not allowed")
    return urlunparse(("https", parsed.netloc, parsed.path, parsed.params, parsed.query, ""))


_GUID_RE = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_DNS_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_DNS_NAME_RE = re.compile(r"(?=.{3,253}$)" + _DNS_LABEL + r"(?:\." + _DNS_LABEL + r")+")
# A dot-atom local part (RFC 5322 section 3.2.3). It may hold ' and & (o'brien@...): pages escape it when they show it.
_ATEXT = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]"
_PLAIN_LOCAL_PART_RE = re.compile(_ATEXT + r"+(?:\." + _ATEXT + r"+)*")
# A Microsoft Graph permission value as it appears in an access token's ``roles`` claim, such as ``Mail.Send``.
_GRAPH_PERMISSION_RE = re.compile(r"[A-Za-z][A-Za-z0-9.]{0,63}")


def is_guid(value: str) -> bool:
    """Whether *value* is a canonical GUID (Entra application, tenant and object IDs)."""
    return bool(_GUID_RE.fullmatch(str(value or "")))


def is_graph_permission(value) -> bool:
    """Whether *value* is a Microsoft Graph permission name such as ``Mail.Send`` (safe to show and compare)."""
    return isinstance(value, str) and bool(_GRAPH_PERMISSION_RE.fullmatch(value))


def is_entra_tenant(value: str) -> bool:
    """Whether *value* is a tenant GUID or a verified domain such as ``contoso.onmicrosoft.com``.

    ``common``, ``organizations`` and ``consumers`` have no dot and are not valid for app-only tokens.
    The value becomes a URL path segment, so anything beyond a GUID or a DNS name is rejected.
    """
    text = str(value or "")
    return is_guid(text) or bool(_DNS_NAME_RE.fullmatch(text))


def is_exchange_mailbox(value: str) -> bool:
    """Whether *value* is a mailbox address / user principal name, or a user object-id GUID."""
    text = str(value or "")
    if is_guid(text):
        return True
    try:
        validate_email(text)
    except ValidationError:
        return False
    return True


def is_plain_address(value: str) -> bool:
    """Whether *value* is a bare ``local@domain`` address: a dot-atom local part and an ASCII DNS domain name.

    Quoted local parts, display names, comments, address literals, whitespace and line breaks are refused, so the
    value can be handed to a mail provider as exactly one recipient. It may still contain ``'`` and ``&``, which
    are valid in a local part: escape it like any other text before showing it.
    """
    text = str(value or "")
    local, separator, domain = text.rpartition("@")
    if not separator or not _PLAIN_LOCAL_PART_RE.fullmatch(local) or not _DNS_NAME_RE.fullmatch(domain):
        return False
    try:
        validate_email(text)
    except ValidationError:
        return False
    return True
