"""The mailboxes Mail -> Inbox reads: every configured account the site may read, in one universal inbox.

* Microsoft Graph: every mailbox in the active Graph configuration's scope with read permission (the sending
  mailbox first). ``GraphMailboxReader`` re-checks the scope on every read.
* Gmail IMAP: the active ``GmailAccessAccount`` (also the "Import from Gmail" account), and any other account that
  opts in with ``show_in_inbox``.

The first account is the default one (what the Inbox read before it held several accounts: Graph when it may read
the sending mailbox, else the Gmail account). Requests name an account by its ``key``; a key is honoured only when
it is one of the accounts listed here, so a hand-written key never reaches a mailbox outside the configuration.
"""

from dataclasses import dataclass

from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError

from apps.core.models import EmailServiceConfig, GmailAccessAccount, MicrosoftGraphProviderConfig

from .connection import InboxError

GRAPH_ACCOUNT = "graph"
IMAP_ACCOUNT = "imap"
ALL_ACCOUNTS = "all"
GRAPH_SOURCE = "Microsoft Graph"

ACCOUNT_UNAVAILABLE_MESSAGE = "That mailbox is not available in the Inbox."
NO_ACCOUNTS_MESSAGE = "No inbox account is configured."


@dataclass(frozen=True)
class InboxAccount:
    """One mailbox the Inbox reads. ``key`` names it in URLs and caches (``graph:<mailbox>`` or ``imap:<row id>``)."""

    key: str
    kind: str
    address: str
    source: str
    gmail_account_id: int | None = None

    @property
    def is_graph(self) -> bool:
        return self.kind == GRAPH_ACCOUNT

    @property
    def source_label(self) -> str:
        return "Source" if self.is_graph else "IMAP host"

    @property
    def label(self) -> str:
        kind = GRAPH_SOURCE if self.is_graph else "Gmail IMAP"
        return f"{self.address} ({kind})"


def readable_accounts() -> list[InboxAccount]:
    """Every account the Inbox reads, the default one first. Empty when nothing is configured."""
    try:
        return [*_graph_accounts(), *_imap_accounts()]
    except (OperationalError, ProgrammingError) as exc:
        raise InboxError("Mail configuration is unavailable. Run the latest migrations first.") from exc


def resolve_account(key: str | None = None) -> InboxAccount:
    """The account *key* names (None or "": the default account). Raises ``InboxError`` for any other key."""
    accounts = readable_accounts()
    if not accounts:
        raise InboxError(NO_ACCOUNTS_MESSAGE)
    if not key:
        return accounts[0]
    for account in accounts:
        if account.key == key:
            return account
    raise InboxError(ACCOUNT_UNAVAILABLE_MESSAGE)


def _graph_accounts() -> list[InboxAccount]:
    graph = MicrosoftGraphProviderConfig.load()
    if not graph.is_configured:
        return []
    sender = graph.sender_mailbox(EmailServiceConfig.load().from_email)
    mailboxes = sorted(
        (scope.mailbox for scope in graph.mailbox_scopes.all() if scope.grants("read")),
        key=lambda mailbox: (mailbox != sender, mailbox),
    )
    return [
        InboxAccount(key=f"{GRAPH_ACCOUNT}:{mailbox}", kind=GRAPH_ACCOUNT, address=mailbox, source=GRAPH_SOURCE)
        for mailbox in mailboxes
    ]


def _imap_accounts() -> list[InboxAccount]:
    rows = GmailAccessAccount.objects.filter(Q(is_active=True) | Q(show_in_inbox=True)).order_by(
        "-is_active", "gmail_username", "pk"
    )
    accounts, seen = [], set()
    for row in rows:
        login = (row.imap_host.strip().lower(), row.gmail_username.strip().lower())
        if not row.is_configured or login in seen:
            continue
        seen.add(login)
        accounts.append(
            InboxAccount(
                key=f"{IMAP_ACCOUNT}:{row.pk}",
                kind=IMAP_ACCOUNT,
                address=row.gmail_username.strip(),
                source=row.imap_host,
                gmail_account_id=row.pk,
            )
        )
    return accounts
