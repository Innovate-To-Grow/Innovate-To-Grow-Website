"""Read a mailbox through Microsoft Graph: folder listings and raw MIME, never changing anything.

Only GET requests are made, and the transport refuses any other request before connecting, so opening a message
here never marks it read in Outlook, and nothing is moved or deleted, even while the app holds ``Mail.ReadWrite``.

Every request is paced on the ``graph_read`` delivery channel, which shares its cooldowns with the mailbox's sends
(Outlook limits each app and mailbox): a read waits at most ``waits.read_seconds`` for its slot.
"""

import json
import logging
import re
from datetime import UTC, datetime
from urllib.parse import quote

from django.conf import settings

from apps.core.models.base.delivery_rates import DeliveryChannel
from apps.core.services.delivery_rates import RateDeferred, WaitMode, admit, mailbox_identity, record, release, wait_cap
from apps.core.services.delivery_rates.adapters.graph import graph_signal

from ..exceptions import EmailDeliveryError
from . import auth, transport
from .access import READ, credential_for, require_mailbox
from .errors import graph_error_code, innermost_error_code, request_id, retryable
from .provider import GRAPH_HOST

logger = logging.getLogger(__name__)

# Well-known folder names (Microsoft Graph "mailFolder resource type").
FOLDERS = {"INBOX": "inbox", "SENT": "sentitems"}
LIST_FIELDS = "id,subject,from,toRecipients,receivedDateTime,bodyPreview,isRead"
# What the bounce processor's incremental scan reads of each message (no preview: it opens only bounce candidates).
SCAN_FIELDS = "id,subject,from,receivedDateTime,internetMessageId"
# Graph message IDs are URL-safe base64; anything else is refused before it can become part of a URL.
_MESSAGE_ID_RE = re.compile(r"[A-Za-z0-9_=-]{1,512}")


class GraphReadError(Exception):
    """A mailbox read failed. Messages are generic and carry at most an allow-listed Graph error code."""


class GraphMessageNotFound(GraphReadError):
    pass


class GraphReadBusy(GraphReadError):
    """The read was held back by the delivery rate (Microsoft asked to wait, or reads are paced); nothing was sent."""

    def __init__(self, retry_after: int):
        super().__init__(f"Microsoft Graph is busy; try again in about {retry_after} seconds.")
        self.retry_after = retry_after


def is_message_id(value) -> bool:
    return isinstance(value, str) and bool(_MESSAGE_ID_RE.fullmatch(value))


class GraphMailboxReader:
    """Reads one mailbox that the active config's scope grants read permission on."""

    def __init__(self, config, mailbox: str, *, timeout: float | None = None):
        self.mailbox = require_mailbox(config, mailbox, READ)
        self.credential = credential_for(config)
        self.timeout = auth.request_timeout(timeout)

    def list_messages(self, folder: str, limit: int) -> list[dict]:
        """The newest *limit* messages of a well-known folder, as Graph ``message`` objects (``LIST_FIELDS`` only)."""
        folder_name = FOLDERS.get(str(folder).upper(), FOLDERS["INBOX"])
        top = max(1, min(int(limit), settings.GRAPH_INBOX_MAX_LIST_LIMIT))
        query = f"$top={top}&$select={LIST_FIELDS}&$orderby=receivedDateTime%20desc"
        return self._message_list(f"{self._user_path()}/mailFolders/{folder_name}/messages?{query}")

    def list_received_since(self, folder: str, since: datetime, limit: int) -> list[dict]:
        """Up to *limit* messages of a well-known folder received at or after *since*, oldest first, with
        ``SCAN_FIELDS`` only: the bounce processor's incremental scan, which never lists the whole folder."""
        folder_name = FOLDERS.get(str(folder).upper(), FOLDERS["INBOX"])
        top = max(1, min(int(limit), settings.GRAPH_INBOX_MAX_LIST_LIMIT))
        stamp = since.astimezone(UTC).strftime("%Y-%m-%dT%H%%3A%M%%3A%SZ")
        query = (
            f"$top={top}&$select={SCAN_FIELDS}&$filter=receivedDateTime%20ge%20{stamp}&$orderby=receivedDateTime%20asc"
        )
        return self._message_list(f"{self._user_path()}/mailFolders/{folder_name}/messages?{query}")

    def _message_list(self, path: str) -> list[dict]:
        response = self._get(path, settings.GRAPH_INBOX_LIST_MAX_BYTES)
        try:
            messages = json.loads(response.body)["value"]
        except (ValueError, KeyError, TypeError, RecursionError):
            messages = None
        if response.truncated or not isinstance(messages, list):
            raise GraphReadError("Microsoft Graph returned an unreadable message list.")
        return [message for message in messages if isinstance(message, dict) and is_message_id(message.get("id"))]

    def fetch_mime(self, message_id: str) -> bytes:
        """The message exactly as received (RFC 5322 MIME), including Authentication-Results and threading headers."""
        body, truncated = self.fetch_mime_head(message_id, settings.GRAPH_INBOX_MESSAGE_MAX_BYTES)
        if truncated:
            raise GraphReadError("The message is too large to display here; open it in Outlook.")
        return body

    def fetch_mime_head(self, message_id: str, max_bytes: int) -> tuple[bytes, bool]:
        """At most *max_bytes* of a message's raw MIME, and whether it was cut off (a bounce report's status part
        precedes the returned original message, so the head of a long report is enough)."""
        if not is_message_id(message_id):
            raise GraphMessageNotFound("Message not found.")
        response = self._get(f"{self._user_path()}/messages/{message_id}/$value", max_bytes)
        return response.body, response.truncated

    def _user_path(self) -> str:
        return f"/v1.0/users/{quote(self.mailbox, safe='@')}"

    def _get(self, path: str, max_bytes: int) -> transport.HttpResponse:
        try:
            admission = admit(
                DeliveryChannel.GRAPH_READ, mailbox_identity(self.mailbox), max_wait=wait_cap(WaitMode.READ)
            )
        except RateDeferred as exc:
            raise GraphReadBusy(exc.retry_after) from None
        try:
            response = self._request(path, max_bytes)
        except GraphReadError as exc:
            # A refused or busy token request is Microsoft's answer; an unreachable Graph is not, so the slot is freed.
            signal = getattr(exc.__cause__, "rate_signal", None)
            if signal is None:
                release(admission)
            else:
                record(admission, signal)
            raise
        except BaseException:
            release(admission)
            raise
        record(
            admission, graph_signal(response.status, response.headers, innermost_error_code(response.body), read=True)
        )
        if response.status == 200:
            return response
        self._raise_for(response)

    def _request(self, path: str, max_bytes: int) -> transport.HttpResponse:
        try:
            access_token = auth.get_access_token(self.credential, timeout=self.timeout)
        except EmailDeliveryError as exc:
            raise GraphReadError(str(exc)) from exc
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            return transport.get(GRAPH_HOST, path, headers, timeout=self.timeout, max_bytes=max_bytes)
        except (transport.ConnectFailed, transport.ResponseLost) as exc:
            raise GraphReadError("Microsoft Graph could not be reached.") from exc
        except transport.RequestNotAllowed as exc:
            raise GraphReadError(str(exc)) from exc

    def _raise_for(self, response: transport.HttpResponse):
        code = graph_error_code(response.body)
        logger.warning(
            "Microsoft Graph mailbox read was refused: status=%s code=%s request_id=%s",
            response.status,
            code or "-",
            request_id(response.headers) or "-",
        )
        detail = f" ({code})" if code else ""
        if response.status in (401, 403):
            auth.forget_access_token(self.credential)
        if response.status == 404:
            raise GraphMessageNotFound("Message not found.")
        if response.status == 403:
            raise GraphReadError(f"Microsoft Graph denied access to {self.mailbox}{detail}.")
        if retryable(response.status):
            raise GraphReadError("Microsoft Graph is busy; try again in a minute.")
        raise GraphReadError(f"Microsoft Graph returned HTTP {response.status}{detail}.")
