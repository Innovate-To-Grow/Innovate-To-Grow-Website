from __future__ import annotations

import logging
from contextlib import contextmanager
from email.utils import parseaddr

from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

DEFAULT_GMAIL_MAILBOX = "i2g@g.ucmerced.edu"
DEFAULT_GMAIL_FOLDER = "Sent"
GMAIL_FOLDER_DISPLAY = "Sent mail (auto-detected)"
SENT_FOLDER_CANDIDATES = (
    DEFAULT_GMAIL_FOLDER,
    "Sent Mail",
    "[Gmail]/Sent Mail",
    "[Google Mail]/Sent Mail",
)


class GmailImportError(RuntimeError):
    """Raised when Gmail message import cannot be completed."""


def normalize_mailbox(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    parsed = parseaddr(normalized)[1]
    return parsed or normalized


def get_gmail_config():
    import mail.services.gmail_import as gmail_api

    try:
        config = gmail_api.GmailImportConfig.load()
    except (OperationalError, ProgrammingError) as exc:
        raise GmailImportError("Gmail import configuration is unavailable. Run the latest migrations first.") from exc
    if not config.is_configured:
        raise GmailImportError("No active Gmail import account is configured.")
    return config


def resolve_gmail_mailbox(mailbox: str | None = None) -> str:
    explicit_mailbox = normalize_mailbox(str(mailbox or "").strip())
    if explicit_mailbox:
        return explicit_mailbox

    import mail.services.gmail_import as gmail_api

    try:
        config = gmail_api.GmailImportConfig.load()
    except (OperationalError, ProgrammingError):
        raise GmailImportError("Gmail import configuration is unavailable. Run the latest migrations first.")
    return normalize_mailbox(config.mailbox) or DEFAULT_GMAIL_MAILBOX


@contextmanager
def _open_mailbox(mailbox: str | None = None):
    config = get_gmail_config()
    resolved_mailbox = resolve_gmail_mailbox(mailbox or config.mailbox)
    try:
        import mail.services.gmail_import as gmail_api

        with gmail_api.MailBox(config.imap_host).login(
            resolved_mailbox,
            config.gmail_password,
            initial_folder=None,
        ) as client:
            select_sent_folder(client)
            yield client
    except GmailImportError:
        raise
    except Exception as exc:  # pragma: no cover - exercised in tests with mocks
        logger.exception(
            "Failed to connect to Gmail IMAP for mailbox %s.",
            resolved_mailbox,
        )
        raise GmailImportError(f"Unable to connect to Gmail for {resolved_mailbox}.") from exc


def iter_sent_folder_candidates(client) -> tuple[str, ...]:
    candidates: list[str] = []
    for folder_name in SENT_FOLDER_CANDIDATES:
        if folder_name not in candidates:
            candidates.append(folder_name)

    try:
        for folder_info in client.folder.list():
            folder_name = str(getattr(folder_info, "name", "") or "").strip()
            folder_flags = tuple(getattr(folder_info, "flags", ()) or ())
            if "\\Sent" in folder_flags and folder_name and folder_name not in candidates:
                candidates.append(folder_name)
    except Exception:
        logger.debug(
            "Unable to enumerate IMAP folders while selecting sent mail.",
            exc_info=True,
        )

    return tuple(candidates)


def select_sent_folder(client) -> str:
    for folder_name in iter_sent_folder_candidates(client):
        try:
            client.folder.set(folder_name)
        except Exception:
            logger.debug(
                "Unable to select IMAP sent-mail candidate %s.",
                folder_name,
                exc_info=True,
            )
        else:
            return folder_name
    raise GmailImportError("Unable to open the sent-mail folder for the configured Gmail account.")
