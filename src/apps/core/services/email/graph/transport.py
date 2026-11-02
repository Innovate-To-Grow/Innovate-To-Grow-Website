"""Bounded HTTPS transport for the fixed Microsoft endpoints used by the Graph provider and mailbox reader.

Only the requests in ``ALLOWED_REQUESTS`` are ever made: the token request, ``sendMail``, the Inbox / Sent Items
message lists, the Inbox folder probe and a message's raw MIME. Anything else (any PATCH, PUT or DELETE, drafts,
replies, moves, other folders or resources) is refused before a connection opens, so the site cannot create,
change or delete mail even while the Entra app holds a broader grant than it needs (such as ``Mail.ReadWrite``).
"""

import re

from django.conf import settings

from ..exceptions import PermanentEmailDeliveryError
from ..transport import ConnectFailed, HttpResponse, ResponseLost, request

USER_AGENT = "i2g-graph-client/1"
AUTHORITY_HOST = "login.microsoftonline.com"
GRAPH_HOST = "graph.microsoft.com"

# One percent-encoded path segment (a tenant or a mailbox): never only dots, never an encoded ".", "/" or "\".
_SEGMENT = r"(?=[^/?]*[A-Za-z0-9])(?:[A-Za-z0-9._~@-]|%(?!2[EeFf]|5[Cc])[0-9A-Fa-f]{2}){1,320}"
_QUERY = r"(?:\?[A-Za-z0-9$=&%,._-]{1,2048})?"
_USER = rf"/v1\.0/users/{_SEGMENT}"
ALLOWED_REQUESTS = (
    ("POST", AUTHORITY_HOST, re.compile(rf"/{_SEGMENT}/oauth2/v2\.0/token")),
    ("POST", GRAPH_HOST, re.compile(rf"{_USER}/sendMail")),
    ("GET", GRAPH_HOST, re.compile(rf"{_USER}/mailFolders/(?:inbox|sentitems)/messages{_QUERY}")),
    ("GET", GRAPH_HOST, re.compile(rf"{_USER}/mailFolders/inbox{_QUERY}")),
    ("GET", GRAPH_HOST, re.compile(rf"{_USER}/messages/[A-Za-z0-9_=-]{{1,512}}/\$value")),
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
