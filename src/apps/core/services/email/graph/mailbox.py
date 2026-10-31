"""Read a mailbox through Microsoft Graph: folder listings and raw MIME, never changing anything.

Only GET requests are made, and the transport refuses any other request before connecting, so opening a message
here never marks it read in Outlook, and nothing is moved or deleted, even while the app holds ``Mail.ReadWrite``.
"""

import json
import logging
import re
from urllib.parse import quote

from ..exceptions import EmailDeliveryError
from . import auth, transport
from .access import READ, credential_for, require_mailbox
from .errors import graph_error_code, request_id
from .provider import GRAPH_HOST

logger = logging.getLogger(__name__)

LIST_MAX_BYTES = 2 * 1024 * 1024
MIME_MAX_BYTES = 25 * 1024 * 1024
MAX_LIST_LIMIT = 100
# Well-known folder names (Microsoft Graph "mailFolder resource type").
FOLDERS = {"INBOX": "inbox", "SENT": "sentitems"}
LIST_FIELDS = "id,subject,from,toRecipients,receivedDateTime,bodyPreview,isRead"
# Graph message IDs are URL-safe base64; anything else is refused before it can become part of a URL.
_MESSAGE_ID_RE = re.compile(r"[A-Za-z0-9_=-]{1,512}")
_RETRYABLE_STATUSES = {408, 429, 503}


class GraphReadError(Exception):
    """A mailbox read failed. Messages are generic and carry at most an allow-listed Graph error code."""


class GraphMessageNotFound(GraphReadError):
    pass


def is_message_id(value) -> bool:
    return isinstance(value, str) and bool(_MESSAGE_ID_RE.fullmatch(value))


class GraphMailboxReader:
    """Reads one mailbox that the active config's scope grants read permission on."""

    def __init__(self, config, mailbox: str, *, timeout: float = auth.REQUEST_TIMEOUT):
        self.mailbox = require_mailbox(config, mailbox, READ)
        self.credential = credential_for(config)
        self.timeout = timeout

    def list_messages(self, folder: str, limit: int) -> list[dict]:
        """The newest *limit* messages of a well-known folder, as Graph ``message`` objects (``LIST_FIELDS`` only)."""
        folder_name = FOLDERS.get(str(folder).upper(), FOLDERS["INBOX"])
        top = max(1, min(int(limit), MAX_LIST_LIMIT))
        query = f"$top={top}&$select={LIST_FIELDS}&$orderby=receivedDateTime%20desc"
        response = self._get(f"{self._user_path()}/mailFolders/{folder_name}/messages?{query}", LIST_MAX_BYTES)
        try:
            messages = json.loads(response.body)["value"]
        except (ValueError, KeyError, TypeError, RecursionError):
            messages = None
        if response.truncated or not isinstance(messages, list):
            raise GraphReadError("Microsoft Graph returned an unreadable message list.")
        return [message for message in messages if isinstance(message, dict) and is_message_id(message.get("id"))]

    def fetch_mime(self, message_id: str) -> bytes:
        """The message exactly as received (RFC 5322 MIME), including Authentication-Results and threading headers."""
        if not is_message_id(message_id):
            raise GraphMessageNotFound("Message not found.")
        response = self._get(f"{self._user_path()}/messages/{message_id}/$value", MIME_MAX_BYTES)
        if response.truncated:
            raise GraphReadError("The message is too large to display here; open it in Outlook.")
        return response.body

    def _user_path(self) -> str:
        return f"/v1.0/users/{quote(self.mailbox, safe='@')}"

    def _get(self, path: str, max_bytes: int) -> transport.HttpResponse:
        try:
            access_token = auth.get_access_token(self.credential, timeout=self.timeout)
        except EmailDeliveryError as exc:
            raise GraphReadError(str(exc)) from exc
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        try:
            response = transport.get(GRAPH_HOST, path, headers, timeout=self.timeout, max_bytes=max_bytes)
        except (transport.ConnectFailed, transport.ResponseLost) as exc:
            raise GraphReadError("Microsoft Graph could not be reached.") from exc
        except transport.RequestNotAllowed as exc:
            raise GraphReadError(str(exc)) from exc
        if response.status == 200:
            return response
        self._raise_for(response)

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
        if response.status in _RETRYABLE_STATUSES:
            raise GraphReadError("Microsoft Graph is busy; try again in a minute.")
        raise GraphReadError(f"Microsoft Graph returned HTTP {response.status}{detail}.")
