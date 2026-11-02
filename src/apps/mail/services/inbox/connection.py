import logging
from contextlib import contextmanager

from django.db.utils import OperationalError, ProgrammingError
from imap_tools import MailBox

from apps.core.models import GmailAccessAccount
from apps.core.services.delivery_rates import RateDeferred

logger = logging.getLogger(__name__)

INBOX_LIST_CACHE_KEY = "inbox:list"
INBOX_LIMIT_CHOICES = [15, 30, 50, 100]
INBOX_LIST_CACHE_TTL = 300
INBOX_MSG_CACHE_PREFIX = "inbox:msg:"
INBOX_MSG_CACHE_TTL = 1800
# The last list read, shown with a banner while reads are held back. Opened messages are kept this long already, so
# the stale list shows nothing older than they do.
INBOX_STALE_LIST_CACHE_PREFIX = "inbox:stale:"
INBOX_STALE_LIST_CACHE_TTL = INBOX_MSG_CACHE_TTL

INBOX_FOLDER = "INBOX"
SENT_FOLDER = "SENT"
INBOX_FOLDER_CHOICES = (INBOX_FOLDER, SENT_FOLDER)


class InboxError(RuntimeError):
    """Raised when an inbox operation cannot be completed."""


class InboxBusy(InboxError):
    """The read was held back by the delivery rate (Gmail or Microsoft asked to wait, or a breaker holds the
    account): nothing was read. ``retry_after`` is the wait in seconds; a list read also carries the last list it
    loaded as ``stale`` (None when none is cached)."""

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after
        self.stale = None


def get_gmail_config() -> GmailAccessAccount:
    try:
        config = GmailAccessAccount.load()
    except (OperationalError, ProgrammingError) as exc:
        raise InboxError("Gmail configuration is unavailable. Run the latest migrations first.") from exc
    if not config.is_configured:
        raise InboxError("No active Gmail import account is configured.")
    return config


def resolve_mailbox(mailbox: str | None = None) -> str:
    from apps.mail.services.gmail_import import resolve_gmail_mailbox

    return resolve_gmail_mailbox(mailbox)


def _select_sent_folder(client) -> None:
    from apps.mail.services.gmail_import.connection import GmailImportError, select_sent_folder

    try:
        select_sent_folder(client)
    except GmailImportError as exc:
        raise InboxError(str(exc)) from exc


@contextmanager
def _open_inbox(mailbox: str | None = None, folder: str = INBOX_FOLDER):
    # gmail_import is imported lazily (like resolve_mailbox) to avoid an inbox -> gmail_import cycle.
    from apps.mail.services.gmail_import.session import busy_text, gmail_imap_session

    config = get_gmail_config()
    resolved_mailbox = resolve_mailbox(mailbox or config.mailbox)
    # parse_folder already enforces the {INBOX, SENT} allowlist; any non-SENT value
    # (incl. an unexpected one) routes to INBOX below.
    normalized_folder = str(folder or INBOX_FOLDER).upper()
    use_sent = normalized_folder == SENT_FOLDER
    try:
        with gmail_imap_session(
            MailBox,
            config,
            resolved_mailbox,
            # The Sent mailbox name varies by provider, so select it after login.
            initial_folder=None if use_sent else INBOX_FOLDER,
        ) as client:
            if use_sent:
                _select_sent_folder(client)
            yield client
    except RateDeferred as exc:
        raise InboxBusy(busy_text(exc), exc.retry_after) from None
    except InboxError:
        raise
    except Exception as exc:
        logger.exception("Failed to connect to Gmail IMAP %s folder for %s.", normalized_folder, resolved_mailbox)
        raise InboxError(f"Unable to connect to inbox for {resolved_mailbox}.") from exc
