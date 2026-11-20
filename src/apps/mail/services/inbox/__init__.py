"""Universal inbox and reply service: every configured mailbox (Microsoft Graph scopes with read, Gmail IMAP
accounts) is read (``accounts``), and a reply may be sent From any configured sending address (``senders``) through
the email facade."""

from .accounts import ALL_ACCOUNTS, InboxAccount, connectable_accounts, readable_accounts, resolve_account
from .connection import (
    INBOX_FOLDER,
    INBOX_FOLDER_CHOICES,
    INBOX_LIMIT_CHOICES,
    SENT_FOLDER,
    InboxBusy,
    InboxError,
    _open_inbox,
)
from .graph_backend import graph_inbox_active
from .messages import InboxListing, fetch_inbox_message, list_all_inbox_messages, list_inbox_messages
from .reply import render_reply_html, send_reply
from .senders import DEFAULT_SENDER, SendIdentity, default_identity_for, resolve_identity, send_identities

__all__ = [
    "ALL_ACCOUNTS",
    "DEFAULT_SENDER",
    "INBOX_FOLDER",
    "INBOX_FOLDER_CHOICES",
    "INBOX_LIMIT_CHOICES",
    "SENT_FOLDER",
    "InboxBusy",
    "InboxAccount",
    "InboxError",
    "InboxListing",
    "SendIdentity",
    "_open_inbox",
    "connectable_accounts",
    "default_identity_for",
    "fetch_inbox_message",
    "graph_inbox_active",
    "list_all_inbox_messages",
    "list_inbox_messages",
    "readable_accounts",
    "render_reply_html",
    "resolve_account",
    "resolve_identity",
    "send_identities",
    "send_reply",
]
