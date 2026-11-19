"""Bounded HTTPS transport for the fixed Microsoft endpoints used by the Graph provider and mailbox reader.

Only the requests in ``ALLOWED_REQUESTS`` are ever made: the token request, ``sendMail``, the Inbox / Sent Items
message lists, the Inbox folder probe, a message's raw MIME and (only while the opt-in Message Trace sync is on) the
Message Trace list of one sender. Anything else (any PATCH, PUT or DELETE, drafts, replies, moves, other folders or
resources) is refused before a connection opens, so the site cannot create, change or delete mail even while the
Entra app holds a broader grant than it needs (such as ``Mail.ReadWrite``). The Message Trace pattern requires the
sender filter and a bounded received-time window, so the tenant's whole trace can never be listed.
"""

import re

from django.conf import settings

from ...sending.exceptions import PermanentEmailDeliveryError
from ...sending.transport import ConnectFailed, HttpResponse, ResponseLost, request

USER_AGENT = "i2g-graph-client/1"
AUTHORITY_HOST = "login.microsoftonline.com"
GRAPH_HOST = "graph.microsoft.com"

# One percent-encoded path segment (a tenant or a mailbox): never only dots, never an encoded ".", "/" or "\".
_SEGMENT = r"(?=[^/?]*[A-Za-z0-9])(?:[A-Za-z0-9._~@-]|%(?!2[EeFf]|5[Cc])[0-9A-Fa-f]{2}){1,320}"
_QUERY = r"(?:\?[A-Za-z0-9$=&%,._-]{1,2048})?"
_USER = rf"/v1\.0/users/{_SEGMENT}"
# Message Trace (``tracing.reader``): exactly one sender (percent-encoded, never an encoded quote, so the OData string
# cannot be closed early), a received-time window, a page size and optionally the re-quoted skip token of the next page.
_SENDER = r"(?:[A-Za-z0-9._~-]|%(?!27)[0-9A-Fa-f]{2}){3,320}"
_STAMP = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}%3A[0-9]{2}%3A[0-9]{2}Z"
_TRACE = (
    rf"/v1\.0/admin/exchange/tracing/messageTraces\?\$filter=senderAddress%20eq%20%27{_SENDER}%27"
    rf"%20and%20receivedDateTime%20ge%20{_STAMP}%20and%20receivedDateTime%20le%20{_STAMP}"
    r"&\$top=[1-9][0-9]{0,3}(?:&\$skiptoken=(?:[A-Za-z0-9._-]|%[0-9A-F]{2}){1,2048})?"
)
ALLOWED_REQUESTS = (
    ("POST", AUTHORITY_HOST, re.compile(rf"/{_SEGMENT}/oauth2/v2\.0/token")),
    ("POST", GRAPH_HOST, re.compile(rf"{_USER}/sendMail")),
    ("GET", GRAPH_HOST, re.compile(rf"{_USER}/mailFolders/(?:inbox|sentitems)/messages{_QUERY}")),
    ("GET", GRAPH_HOST, re.compile(rf"{_USER}/mailFolders/inbox{_QUERY}")),
    ("GET", GRAPH_HOST, re.compile(rf"{_USER}/messages/[A-Za-z0-9_=-]{{1,512}}/\$value")),
    ("GET", GRAPH_HOST, re.compile(_TRACE)),
)


class RequestNotAllowed(PermanentEmailDeliveryError):
    """The request is not one the site makes; nothing was sent."""

    def __init__(self):
        super().__init__("The site does not make this Microsoft Graph request.")


def is_allowed(method: str, host: str, path: str) -> bool:
    return any(
        method == allowed_method and host == allowed_host and pattern.fullmatch(path)
        for allowed_method, allowed_host, pattern in ALLOWED_REQUESTS
    )


def post(host: str, path: str, body: bytes, headers: dict[str, str], *, timeout: float) -> HttpResponse:
    """POST *body* to ``https://{host}{path}`` without redirects, proxies or unbounded reads (``email.transport``).

    Raises ``ConnectFailed`` when provably nothing was sent and ``ResponseLost`` when the outcome is unknown.
    """
    return _request("POST", host, path, body, headers, timeout=timeout, max_bytes=settings.GRAPH_MAX_RESPONSE_BYTES)


def get(host: str, path: str, headers: dict[str, str], *, timeout: float, max_bytes: int) -> HttpResponse:
    """GET ``https://{host}{path}`` with the same guarantees as ``post``, reading at most *max_bytes* of body.

    A longer body is cut off and flagged ``truncated``, so a caller never mistakes part of a message for all of it.
    """
    return _request("GET", host, path, None, headers, timeout=timeout, max_bytes=max_bytes)


def _request(method, host, path, body, headers, *, timeout, max_bytes) -> HttpResponse:
    if not is_allowed(method, host, path):
        raise RequestNotAllowed()
    return request(method, host, path, body, headers, timeout=timeout, max_bytes=max_bytes, user_agent=USER_AGENT)


__all__ = [
    "ALLOWED_REQUESTS",
    "AUTHORITY_HOST",
    "GRAPH_HOST",
    "USER_AGENT",
    "ConnectFailed",
    "HttpResponse",
    "RequestNotAllowed",
    "ResponseLost",
    "get",
    "is_allowed",
    "post",
]
