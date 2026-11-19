"""Read Microsoft Graph Message Trace for one sender: ``GET /v1.0/admin/exchange/tracing/messageTraces``.

Every request names the sender and a received-time window (the transport's allow-list refuses any other trace
query, so the tenant's whole trace can never be listed). The next page is never followed as Microsoft links it: only
the ``$skiptoken`` of ``@odata.nextLink`` is taken, after its scheme, host and path were checked, and the query is
rebuilt here. A response is read up to ``trace_max_bytes``; a longer one is an error, never a partial list.

Trace requests are not paced on the mailbox's delivery-rate lane: Message Trace is a tenant-wide API, and its 429 or
401/403 must never pause or stop *sending*. Rows stay in memory; recipients, subjects and IPs are never logged.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, unquote, urlsplit

from ...sending.exceptions import EmailDeliveryError
from .. import transport
from ..identity import auth
from ..identity.access import credential_for
from ..transport.errors import graph_error_code, request_id, retry_after_seconds
from . import limits

logger = logging.getLogger(__name__)

TRACE_PATH = "/v1.0/admin/exchange/tracing/messageTraces"
# Microsoft's own limit on one query's window is ten days; the sync asks for one day at most.
MAX_WINDOW = timedelta(hours=24)
_BUSY_STATUSES = (429, 503)
_DENIED_STATUSES = (401, 403)
_MAX_SKIPTOKEN = 2048


class GraphTraceError(Exception):
    """A trace read failed. Messages are generic and carry at most an allow-listed Graph error code."""


class GraphTraceBusy(GraphTraceError):
    """Microsoft asked to wait (429 or 503); ``retry_after`` is its Retry-After in seconds, or None."""

    def __init__(self, retry_after: float | None):
        super().__init__("Microsoft Graph Message Trace is busy; it will be tried again later.")
        self.retry_after = retry_after


class GraphTraceNotPermitted(GraphTraceError):
    """Microsoft refused the trace (401 or 403): the permission, its consent or its service principal is missing."""

    def __init__(self, status: int, code: str = ""):
        detail = f" ({code})" if code else ""
        super().__init__(f"Microsoft Graph refused Message Trace (HTTP {status}){detail}.")
        self.status = status


@dataclass(frozen=True)
class TracePage:
    rows: list[dict]
    skiptoken: str = ""  # the next page's, already re-quoted; "" on the last page


def stamp(moment: datetime) -> str:
    """An OData DateTimeOffset literal in UTC, its colons percent-encoded."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H%%3A%M%%3A%SZ")


def requote(token: str) -> str:
    """A skip token percent-encoded with nothing left reserved (``~`` included), as the allow-list expects."""
    return quote(token, safe="").replace("~", "%7E")


def trace_query(sender: str, start: datetime, end: datetime, top: int, skiptoken: str = "") -> str:
    """The full path and query of one trace page; *skiptoken* must already be re-quoted (``requote``)."""
    literal = quote(sender, safe="").replace("~", "%7E")
    query = (
        f"$filter=senderAddress%20eq%20%27{literal}%27%20and%20receivedDateTime%20ge%20{stamp(start)}"
        f"%20and%20receivedDateTime%20le%20{stamp(end)}&$top={top}"
    )
    if skiptoken:
        query += f"&$skiptoken={skiptoken}"
    return f"{TRACE_PATH}?{query}"


def next_skiptoken(link) -> str:
    """The re-quoted ``$skiptoken`` of an ``@odata.nextLink``; "" when there is none. A link to anywhere but this
    API on Graph's own host, or one without exactly one skip token, is an error."""
    if link is None:
        return ""
    try:
        parts = urlsplit(link) if isinstance(link, str) else None
        port = parts.port if parts is not None else None
    except ValueError:
        parts = port = None
    if parts is None or parts.scheme != "https" or parts.netloc != transport.GRAPH_HOST or port is not None:
        raise GraphTraceError("Microsoft Graph returned an unexpected next-page link.")
    if parts.path != TRACE_PATH or parts.fragment:
        raise GraphTraceError("Microsoft Graph returned an unexpected next-page link.")
    # Split by hand: ``parse_qs`` would read a literal "+" in the token as a space.
    pairs = (item.partition("=") for item in parts.query.split("&"))
    tokens = [unquote(value) for key, _sep, value in pairs if unquote(key) == "$skiptoken"]
    token = requote(tokens[0]) if len(tokens) == 1 else ""
    if not token or len(token) > _MAX_SKIPTOKEN:
        raise GraphTraceError("Microsoft Graph returned an unreadable next-page link.")
    return token


class GraphTraceReader:
    """Reads the Message Trace of one sender address with the active config's certificate."""

    def __init__(self, config, sender: str, *, timeout: float | None = None):
        self.sender = sender
        self.credential = credential_for(config)
        self.timeout = auth.request_timeout(timeout)

    def access_token(self, *, fresh: bool = False) -> tuple[str, bool]:
        """The access token every trace request uses, and whether it was just issued (False: served from the cache).
        *fresh* drops the cached one first: a cached token's roles are those of when it was issued, before a grant."""
        if fresh:
            auth.forget_access_token(self.credential)
        try:
            return auth.obtain_access_token(self.credential, timeout=self.timeout)
        except EmailDeliveryError as exc:
            raise GraphTraceError(str(exc)) from exc

    def page(self, start: datetime, end: datetime, *, top: int | None = None, skiptoken: str = "") -> TracePage:
        """One page of the sender's trace received in ``[start, end]`` (at most one day)."""
        if not start <= end <= start + MAX_WINDOW:
            raise ValueError("A Message Trace window is at most one day.")
        size = limits.page_size() if top is None else max(1, min(int(top), limits.page_size()))
        response = self._get(trace_query(self.sender, start, end, size, skiptoken))
        try:
            data = json.loads(response.body)
            rows = data["value"]
        except (ValueError, KeyError, TypeError, RecursionError):
            rows = None
        if not isinstance(rows, list):
            raise GraphTraceError("Microsoft Graph returned an unreadable Message Trace list.")
        return TracePage([row for row in rows if isinstance(row, dict)], next_skiptoken(data.get("@odata.nextLink")))

    def _get(self, path: str) -> transport.HttpResponse:
        headers = {"Authorization": f"Bearer {self.access_token()[0]}", "Accept": "application/json"}
        try:
            response = transport.get(
                transport.GRAPH_HOST, path, headers, timeout=self.timeout, max_bytes=limits.max_bytes()
            )
        except (transport.ConnectFailed, transport.ResponseLost) as exc:
            raise GraphTraceError("Microsoft Graph could not be reached.") from exc
        except transport.RequestNotAllowed as exc:
            raise GraphTraceError(str(exc)) from exc
        if response.status == 200 and response.truncated:
            raise GraphTraceError("The Message Trace response exceeded trace_max_bytes; it was not used.")
        if response.status == 200:
            return response
        self._raise_for(response)

    def _raise_for(self, response: transport.HttpResponse):
        code = graph_error_code(response.body)
        logger.warning(
            "Microsoft Graph Message Trace was refused: status=%s code=%s request_id=%s",
            response.status,
            code or "-",
            request_id(response.headers) or "-",
        )
        if response.status in _BUSY_STATUSES:
            raise GraphTraceBusy(retry_after_seconds(response.headers))
        if response.status in _DENIED_STATUSES:
            auth.forget_access_token(self.credential)
            raise GraphTraceNotPermitted(response.status, code)
        detail = f" ({code})" if code else ""
        raise GraphTraceError(f"Microsoft Graph returned HTTP {response.status} for Message Trace{detail}.")
