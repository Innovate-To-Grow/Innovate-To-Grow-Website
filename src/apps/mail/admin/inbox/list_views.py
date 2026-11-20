"""Inbox list admin views."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.core.utils.access import user_can_access_app

from . import services as inbox_api
from .helpers import hide_own_mail, parse_account, parse_folder, parse_limit, sent_mail_restricted

# While the inbox page is open and visible it reloads its list this often (from the poller's snapshot and the
# container cache, so it seldom connects to a mailbox).
AUTO_REFRESH_SECONDS = 60


def inbox_list_view(request):
    """Render the inbox shell instantly; JS fetches content asynchronously."""
    # ``admin_view`` only enforces is_staff, so this custom URL must re-check
    # per-app access itself.
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
    (``?refresh=1``) tries every account again.
    """
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access the mail inbox.")
    error_message = busy_message = ""
    showing_stale = False
    inbox_messages = []
    limit = parse_limit(request)
    folder = parse_folder(request)
    sent_folder_allowed = not sent_mail_restricted(request.user)
    if not sent_folder_allowed:
        # The Sent tab is not offered, and a remembered or hand-written ?folder=SENT shows the Inbox instead.
        folder = inbox_api.INBOX_FOLDER
    force_refresh = request.GET.get("refresh") == "1"
    shown, _hidden = _connectable(retry=force_refresh)
    account = parse_account(request, default=inbox_api.ALL_ACCOUNTS)
    if account != inbox_api.ALL_ACCOUNTS and account not in {item.key for item in shown}:
        # A remembered account that is no longer configured, or cannot connect: show every account instead.
        account = inbox_api.ALL_ACCOUNTS

    try:
        if account == inbox_api.ALL_ACCOUNTS:
            listing = inbox_api.list_all_inbox_messages(limit=limit, force_refresh=force_refresh, folder=folder)
            inbox_messages, showing_stale = listing.messages, listing.showing_stale
            busy_message = " ".join(listing.busy)
        else:
            inbox_messages = inbox_api.list_inbox_messages(
                limit=limit, force_refresh=force_refresh, folder=folder, account=account
            )
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
    if not sent_folder_allowed:
        inbox_messages = hide_own_mail(inbox_messages)
    # After the read, which recorded whether each account connected.
    accounts, hidden = _connectable()
    hidden_message = ""
    if hidden:
        hidden_message = (
            f"Not shown because they could not connect: {', '.join(item.address for item in hidden)}. "
            "They are tried again automatically, or now with Refresh."
        )

    return TemplateResponse(
        request,
        "admin/mail/inbox/detail/_inbox_full_body.html",
        {
            "inbox_account": _inbox_account(accounts, account),
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
            "sent_folder_allowed": sent_folder_allowed,
        },
    )


def _connectable(*, retry: bool = False) -> tuple[list, list]:
    """``(shown, hidden)`` inbox accounts (``connectable_accounts``); ``([], [])`` when they cannot be listed."""
    try:
        return inbox_api.connectable_accounts(retry=retry)
    except Exception:
        inbox_api.logger.exception("Could not list the inbox accounts.")
        return [], []


def _inbox_account(accounts: list, selected: str) -> dict[str, str]:
    """Which mailbox the inbox shows and where it is read from (Microsoft Graph or Gmail IMAP)."""
    for account in accounts:
        if account.key == selected:
            return {"account": account.address, "source_label": account.source_label, "source": account.source}
    if not accounts:
        return {"account": "Not configured", "source_label": "Source", "source": "N/A"}
    if len(accounts) == 1:
        only = accounts[0]
        return {"account": only.address, "source_label": only.source_label, "source": only.source}
    return {
        "account": f"All accounts ({len(accounts)})",
        "source_label": "Sources",
        "source": ", ".join(sorted({account.source for account in accounts})),
    }
