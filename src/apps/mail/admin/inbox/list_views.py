"""Inbox list admin views."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.core.models import GmailAccessAccount
from apps.core.utils.access import user_can_access_app
from apps.mail.services.inbox import graph_backend

from . import services as inbox_api
from .helpers import parse_folder, parse_limit, sent_mail_restricted


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
    return TemplateResponse(request, "admin/mail/inbox/list.html", context)


def inbox_fragment_view(request):
    """Return HTML partial for inbox list and config stats."""
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access the mail inbox.")
    error_message = ""
    inbox_messages = []
    limit = parse_limit(request)
    folder = parse_folder(request)
    sent_folder_allowed = not sent_mail_restricted(request.user)
    if not sent_folder_allowed:
        # The Sent tab is not offered, and a remembered or hand-written ?folder=SENT shows the Inbox instead.
        folder = inbox_api.INBOX_FOLDER
    force_refresh = request.GET.get("refresh") == "1"

    try:
        inbox_messages = inbox_api.list_inbox_messages(limit=limit, force_refresh=force_refresh, folder=folder)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox fragment could not be loaded: %s", exc)
        error_message = inbox_api.INBOX_CONFIG_ERROR_MESSAGE
    except Exception:
        inbox_api.logger.exception("Unexpected error refreshing inbox fragment.")
        error_message = inbox_api.INBOX_UNEXPECTED_ERROR_MESSAGE

    return TemplateResponse(
        request,
        "admin/mail/inbox/_inbox_full_body.html",
        {
            "inbox_account": _inbox_account(),
            "inbox_messages": inbox_messages,
            "error_message": error_message,
            "limit": limit,
            "limit_choices": inbox_api.INBOX_LIMIT_CHOICES,
            "folder": folder,
            "sent_folder_allowed": sent_folder_allowed,
        },
    )


def _inbox_account() -> dict[str, str]:
    """Which mailbox the inbox shows and where it is read from (Microsoft Graph or Gmail IMAP)."""
    try:
        reader = graph_backend.active_reader()
    except Exception:
        inbox_api.logger.exception("Could not resolve the Microsoft Graph inbox reader.")
        reader = None
    if reader is not None:
        return {"account": reader.mailbox, "source_label": "Source", "source": "Microsoft Graph"}
    gmail_config = GmailAccessAccount.load()
    return {
        "account": gmail_config.gmail_username or "Not configured",
        "source_label": "IMAP host",
        "source": gmail_config.imap_host or "N/A",
    }
