"""Bounded HTTPS for the fixed endpoints the email providers call (Microsoft Graph and the Gmail API).

``HTTPSConnection`` is used directly (as for the SNS client), so a response cannot redirect a request to an
unvalidated location and ambient proxy settings are ignored, and at most ``max_bytes`` of a body are read.
Connecting first separates failures that provably sent nothing (``ConnectFailed``) from those after which the
outcome is unknown (``ResponseLost``). Each provider keeps the list of requests it makes in its own transport
module and refuses anything else before calling ``request``.
"""

import ssl
from dataclasses import dataclass
from http.client import HTTPException, HTTPSConnection, IncompleteRead


class ConnectFailed(Exception):
    """No connection could be established, so not a single request byte was sent."""

    def __init__(self, *, verification_failed: bool = False):
        super().__init__("connection failed")
        self.verification_failed = verification_failed


class ResponseLost(Exception):
    """The request may have reached the server but no response status was read."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    truncated: bool = False


def request(method, host, path, body, headers, *, timeout, max_bytes, user_agent) -> HttpResponse:
    """One request to ``https://{host}{path}``; a body longer than *max_bytes* is cut off and flagged ``truncated``,
    so a caller never mistakes part of a response for all of it."""
    context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = HTTPSConnection(host, port=443, timeout=timeout, context=context)
    try:
        try:
            connection.connect()
        except ssl.SSLCertVerificationError as exc:
            raise ConnectFailed(verification_failed=True) from exc
        except OSError as exc:
            raise ConnectFailed() from exc
        try:
            connection.request(method, path, body=body, headers={"User-Agent": user_agent, **headers})
            response = connection.getresponse()
        except (OSError, HTTPException) as exc:
            raise ResponseLost() from exc
        content = _read_body(response, max_bytes + 1)
        return HttpResponse(
            status=response.status,
            headers={name.lower(): value for name, value in response.getheaders()},
            body=content[:max_bytes],
            truncated=len(content) > max_bytes,
        )
    finally:
        connection.close()


def _read_body(response, limit: int) -> bytes:
    """Read at most *limit* bytes; the status line already decided the outcome, so a body failure is benign."""
    try:
        return response.read(limit)
    except IncompleteRead as exc:
        return exc.partial
    except (OSError, HTTPException):
        return b""
