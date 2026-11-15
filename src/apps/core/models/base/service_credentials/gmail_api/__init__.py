"""The Gmail API provider: a Google service account with domain-wide delegation (``provider``, with its readiness in
``provider_status``), the facts of its installed key (``key_facts``), and the Workspace users it may send as
(``subjects``).

Migration 0038 imports the two message ceilings' defaults from this package, so it re-exports them from ``limits``.
"""

from .key_facts import CLIENT_ID_RE, KEY_ID_RE, PROJECT_ID_RE, SERVICE_ACCOUNT_EMAIL_RE, VERSION_ID_RE
from .limits import default_max_message_bytes, default_max_recipients
from .provider import (
    ACTIVE_NEEDS_KEY,
    CEILING_HELP,
    MESSAGE_BYTES_HELP,
    RECIPIENTS_HELP,
    TAKEOVER_REFUSED,
    GmailApiProviderConfig,
)
from .provider_status import RUN_THE_CHECK
from .subjects import SUBJECT_FORMAT, GmailApiSubject, is_subject, normalize_subject

__all__ = [
    "ACTIVE_NEEDS_KEY",
    "CEILING_HELP",
    "CLIENT_ID_RE",
    "KEY_ID_RE",
    "MESSAGE_BYTES_HELP",
    "PROJECT_ID_RE",
    "RECIPIENTS_HELP",
    "RUN_THE_CHECK",
    "SERVICE_ACCOUNT_EMAIL_RE",
    "SUBJECT_FORMAT",
    "TAKEOVER_REFUSED",
    "VERSION_ID_RE",
    "GmailApiProviderConfig",
    "GmailApiSubject",
    "default_max_message_bytes",
    "default_max_recipients",
    "is_subject",
    "normalize_subject",
]
