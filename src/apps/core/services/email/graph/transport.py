"""Bounded HTTPS transport for the fixed Microsoft endpoints used by the Graph provider and mailbox reader."""

import ssl
from dataclasses import dataclass
from http.client import HTTPException, HTTPSConnection, IncompleteRead

MAX_RESPONSE_BYTES = 64 * 1024
USER_AGENT = "i2g-graph-client/1"


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


def post(host: str, path: str, body: bytes, headers: dict[str, str], *, timeout: float) -> HttpResponse:
    """POST *body* to ``https://{host}{path}`` without redirects, proxies or unbounded reads.

    ``HTTPSConnection`` is used directly (as for the SNS client) so a response cannot redirect the request to an
    unvalidated location and ambient proxy settings are ignored. Connecting first separates failures that provably
    sent nothing (``ConnectFailed``) from those after which the outcome is unknown (``ResponseLost``).
    """
    return _request("POST", host, path, body, headers, timeout=timeout, max_bytes=MAX_RESPONSE_BYTES)


def get(host: str, path: str, headers: dict[str, str], *, timeout: float, max_bytes: int) -> HttpResponse:
    """GET ``https://{host}{path}`` with the same guarantees as ``post``, reading at most *max_bytes* of body.

    A longer body is cut off and flagged ``truncated``, so a caller never mistakes part of a message for all of it.
    """
    return _request("GET", host, path, None, headers, timeout=timeout, max_bytes=max_bytes)


def _request(method, host, path, body, headers, *, timeout, max_bytes) -> HttpResponse:
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
            connection.request(method, path, body=body, headers={"User-Agent": USER_AGENT, **headers})
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
