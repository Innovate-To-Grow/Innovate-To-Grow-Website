"""Inbox list admin views."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.core.utils.access import user_can_access_app

from . import services as inbox_api
from .helpers import inbox_account_summary, parse_account, parse_folder, parse_limit

# While the inbox page is open and visible it reloads its list this often (from the poller's snapshot and the
# container cache, so it seldom connects to a mailbox).
AUTO_REFRESH_SECONDS = 60
FULL_TEMPLATE = "admin/mail/inbox/detail/_inbox_full_body.html"
# "Load older" (``?older=1&cursor=``): only the next page of rows and its own "Load older" footer.
OLDER_TEMPLATE = "admin/mail/inbox/list/_inbox_older.html"


def inbox_list_view(request):
    """Render the inbox shell instantly; JS fetches content asynchronously."""
    # A plain Admin check, in case the URL is ever mounted without ``admin_view``.
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access the mail inbox.")
    context = {
        **admin.site.each_context(request),
        "title": "Inbox",
        "fragment_url": reverse("admin:mail_inbox_fragment"),
    }
    return TemplateResponse(request, "admin/mail/inbox/list/list.html", context)


def inbox_fragment_view(request):
    """Return HTML partial for inbox list and config stats.

    ``?account=all`` (the default) merges the newest messages of every account that connects; an account key shows
    that one. Accounts that could not connect recently are left out of both and named in a note; Refresh
    (``?refresh=1``) tries every account again. ``?older=1&cursor=<token>`` returns the page after the one the
    cursor ends (``services.inbox.paging``). The accounts' states are loaded once for the whole request.
    """
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access the mail inbox.")
    older = request.GET.get("older") == "1"
    with inbox_api.inbox_state_scope():
        context = _fragment_context(request, older=older)
    return TemplateResponse(request, OLDER_TEMPLATE if older else FULL_TEMPLATE, context)


def _fragment_context(request, *, older: bool) -> dict:
    error_message = busy_message = ""
    showing_stale = False
    inbox_messages = []
    limit = parse_limit(request)
    folder = parse_folder(request)
    force_refresh = request.GET.get("refresh") == "1"
    cursor = inbox_api.paging.decode(request.GET.get("cursor")) if older else {}
    next_cursor = dict(cursor)
    shown, _hidden = _connectable(retry=force_refresh)
    account = parse_account(request, default=inbox_api.ALL_ACCOUNTS)
    by_key = {item.key: item for item in shown}
    if account != inbox_api.ALL_ACCOUNTS and account not in by_key:
        # A remembered account that is no longer configured, or cannot connect: show every account instead.
        account = inbox_api.ALL_ACCOUNTS

    try:
        if account == inbox_api.ALL_ACCOUNTS:
            listing = inbox_api.list_all_inbox_messages(
                limit=limit, force_refresh=force_refresh, folder=folder, cursor=cursor
            )
            inbox_messages, showing_stale, next_cursor = listing.messages, listing.showing_stale, listing.cursor
            busy_message = " ".join(listing.busy)
        else:
            inbox_messages = inbox_api.list_inbox_messages(
                limit=limit, force_refresh=force_refresh, folder=folder, account=account, cursor=cursor
            )
            start = inbox_api.paging.position(cursor, by_key[account])
            if start is not None:
                inbox_api.paging.advance(next_cursor, by_key[account], start, inbox_messages, inbox_messages, limit)
    except inbox_api.InboxBusy as exc:
        # Reads are held back (the provider asked to wait): show the list as last read, with a banner.
        busy_message, showing_stale = str(exc), exc.stale is not None
        inbox_messages = exc.stale or []
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox fragment could not be loaded: %s", exc)
        error_message = inbox_api.INBOX_CONFIG_ERROR_MESSAGE
    except Exception:
        inbox_api.logger.exception("Unexpected error refreshing inbox fragment.")
        error_message = inbox_api.INBOX_UNEXPECTED_ERROR_MESSAGE
    # After the read, which recorded whether each account connected.
    accounts, hidden = _connectable()
    hidden_message = ""
    if hidden:
        hidden_message = (
            f"Not shown because they could not connect: {', '.join(item.address for item in hidden)}. "
            "They are tried again automatically, or now with Refresh."
        )
    return {
        "inbox_account": inbox_account_summary(accounts, account),
        "inbox_accounts": accounts,
        "selected_account": account,
        "all_accounts": inbox_api.ALL_ACCOUNTS,
        "show_account_column": account == inbox_api.ALL_ACCOUNTS and len(accounts) > 1,
        "inbox_messages": inbox_messages,
        "error_message": error_message,
        "busy_message": busy_message,
        "hidden_message": hidden_message,
        "auto_refresh_seconds": AUTO_REFRESH_SECONDS,
        "showing_stale": showing_stale,
        "limit": limit,
        "limit_choices": inbox_api.INBOX_LIMIT_CHOICES,
        "folder": folder,
        "older_page": older,
        # A failed page keeps its cursor, so its Retry reads the same page again.
        "older_cursor": inbox_api.paging.encode(cursor if error_message else next_cursor),
        "has_older": inbox_api.paging.has_more(next_cursor),
    }


def _connectable(*, retry: bool = False) -> tuple[list, list]:
    """``(shown, hidden)`` inbox accounts (``connectable_accounts``); ``([], [])`` when they cannot be listed."""
    try:
        return inbox_api.connectable_accounts(retry=retry)
    except Exception:
        inbox_api.logger.exception("Could not list the inbox accounts.")
        return [], []
