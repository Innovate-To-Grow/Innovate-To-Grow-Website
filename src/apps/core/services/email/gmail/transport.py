"""The Gmail API's fixed requests, over the bounded HTTPS client (``email.transport``).

Only two requests are ever made: the token exchange at ``oauth2.googleapis.com/token`` and the media upload of
``messages.send`` for the authenticated user (``me``). Anything else is refused before a connection opens, so the
site cannot read, change or delete mail even if the delegation were broader than gmail.send.
"""

import threading

from django.conf import settings

from ..exceptions import PermanentEmailDeliveryError
from ..transport import ConnectFailed, HttpResponse, ResponseLost, request

USER_AGENT = "i2g-gmail-client/1"
TOKEN_HOST = "oauth2.googleapis.com"  # nosec B105 - a host name, not a credential
TOKEN_PATH = "/token"  # nosec B105 - a URL path, not a credential
GMAIL_HOST = "gmail.googleapis.com"
SEND_PATH = "/upload/gmail/v1/users/me/messages/send?uploadType=media"
ALLOWED_REQUESTS = frozenset({("POST", TOKEN_HOST, TOKEN_PATH), ("POST", GMAIL_HOST, SEND_PATH)})
# Requests this thread has made: the access check proves with it that a refused subject reached no Google endpoint.
_made = threading.local()


class RequestNotAllowed(PermanentEmailDeliveryError):
    """The request is not one the site makes; nothing was sent."""

    def __init__(self):
        super().__init__("The site does not make this Gmail API request.")


def post(host: str, path: str, body: bytes, headers: dict[str, str], *, timeout: float) -> HttpResponse:
    """POST one of the allowed requests. Raises ``ConnectFailed`` (nothing sent) or ``ResponseLost`` (unknown)."""
    _made.count = requests_made() + 1
    if ("POST", host, path) not in ALLOWED_REQUESTS:
        raise RequestNotAllowed()
    max_bytes = settings.GMAIL_API["max_response_bytes"]
    return request("POST", host, path, body, headers, timeout=timeout, max_bytes=max_bytes, user_agent=USER_AGENT)


def requests_made() -> int:
    """How many requests this thread has asked the transport for (allowed or not)."""
    return getattr(_made, "count", 0)


__all__ = [
    "ALLOWED_REQUESTS",
    "GMAIL_HOST",
    "SEND_PATH",
    "TOKEN_HOST",
    "TOKEN_PATH",
    "USER_AGENT",
    "ConnectFailed",
    "HttpResponse",
    "RequestNotAllowed",
    "ResponseLost",
    "post",
    "requests_made",
]
