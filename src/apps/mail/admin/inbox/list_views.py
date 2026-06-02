"""Inbox list admin views."""

from django.contrib import admin
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import reverse

import apps.mail.admin.inbox as inbox_api
from apps.core.models import GmailAccessAccount

from .helpers import parse_folder, parse_limit


def inbox_list_view(request):
    """Render the inbox shell instantly; JS fetches content asynchronously."""
    context = {
        **admin.site.each_context(request),
        "title": "Gmail Inbox",
        "fragment_url": reverse("admin:mail_inbox_fragment"),
    }
    return TemplateResponse(request, "admin/mail/inbox/list.html", context)


def inbox_fragment_view(request):
    """Return HTML partial for inbox list and config stats."""
    gmail_config = GmailAccessAccount.load()
    error_message = ""
    inbox_messages = []
    limit = parse_limit(request)
    folder = parse_folder(request)
    force_refresh = request.GET.get("refresh") == "1"

    try:
        inbox_messages = inbox_api.list_inbox_messages(limit=limit, force_refresh=force_refresh, folder=folder)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox fragment could not be loaded: %s", exc)
        error_message = inbox_api.INBOX_CONFIG_ERROR_MESSAGE
    except Exception:
        inbox_api.logger.exception("Unexpected error refreshing inbox fragment.")
        error_message = inbox_api.INBOX_UNEXPECTED_ERROR_MESSAGE

    html = render_to_string(
        "admin/mail/inbox/_inbox_full_body.html",
        {
            "gmail_config": gmail_config,
            "inbox_messages": inbox_messages,
            "error_message": error_message,
            "limit": limit,
            "limit_choices": inbox_api.INBOX_LIMIT_CHOICES,
            "folder": folder,
        },
        request=request,
    )
    return HttpResponse(html)
