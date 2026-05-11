import logging
from contextlib import contextmanager

from django.db.utils import OperationalError, ProgrammingError
from imap_tools import MailBox

from core.models import GmailImportConfig

logger = logging.getLogger(__name__)

INBOX_LIST_CACHE_KEY = "inbox:list"
INBOX_LIMIT_CHOICES = [15, 30, 50, 100]
INBOX_LIST_CACHE_TTL = 300
INBOX_MSG_CACHE_PREFIX = "inbox:msg:"
INBOX_MSG_CACHE_TTL = 1800


class InboxError(RuntimeError):
    """Raised when an inbox operation cannot be completed."""


def get_gmail_config() -> GmailImportConfig:
    try:
        config = GmailImportConfig.load()
    except (OperationalError, ProgrammingError) as exc:
        raise InboxError("Gmail configuration is unavailable. Run the latest migrations first.") from exc
    if not config.is_configured:
        raise InboxError("No active Gmail import account is configured.")
    return config


def resolve_mailbox(mailbox: str | None = None) -> str:
    from mail.services.gmail_import import resolve_gmail_mailbox

    return resolve_gmail_mailbox(mailbox)


@contextmanager
def _open_inbox(mailbox: str | None = None):
    config = get_gmail_config()
    resolved_mailbox = resolve_mailbox(mailbox or config.mailbox)
    try:
        with MailBox(config.imap_host).login(
            resolved_mailbox,
            config.gmail_password,
            initial_folder="INBOX",
        ) as client:
            yield client
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to connect to Gmail IMAP inbox for %s.", resolved_mailbox)
        raise InboxError(f"Unable to connect to inbox for {resolved_mailbox}.") from exc
