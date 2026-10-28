"""Bounded HTTPS transport for the fixed Microsoft endpoints used by the Graph provider."""

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


def post(host: str, path: str, body: bytes, headers: dict[str, str], *, timeout: float) -> HttpResponse:
    """POST *body* to ``https://{host}{path}`` without redirects, proxies or unbounded reads.

    ``HTTPSConnection`` is used directly (as for the SNS client) so a response cannot redirect the request to an
    unvalidated location and ambient proxy settings are ignored. Connecting first separates failures that provably
    sent nothing (``ConnectFailed``) from those after which the outcome is unknown (``ResponseLost``).
    """
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
            connection.request("POST", path, body=body, headers={"User-Agent": USER_AGENT, **headers})
            response = connection.getresponse()
        except (OSError, HTTPException) as exc:
            raise ResponseLost() from exc
        return HttpResponse(
            status=response.status,
            headers={name.lower(): value for name, value in response.getheaders()},
            body=_read_body(response),
        )
    finally:
        connection.close()


def _read_body(response) -> bytes:
    """Read at most ``MAX_RESPONSE_BYTES``; the status line already decided the outcome, so a body failure is benign."""
    try:
        return response.read(MAX_RESPONSE_BYTES)
    except IncompleteRead as exc:
        return exc.partial
    except (OSError, HTTPException):
        return b""
