"""Inbox detail admin views."""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import reverse

import apps.mail.admin.inbox as inbox_api
from apps.core.access import user_can_access_app
from apps.core.utils.json_helpers import safe_json

from .helpers import message_body_html, parse_folder


def inbox_detail_view(request, uid):
    """Display a single inbox message."""
    # ``admin_view`` only enforces is_staff, so this custom URL must re-check
    # per-app access itself.
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access the mail inbox.")
    list_url = reverse("admin:mail_inbox_list")
    folder = parse_folder(request)

    try:
        msg = inbox_api.fetch_inbox_message(uid, folder=folder)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox message uid=%s could not be loaded: %s", uid, exc)
        messages.error(request, inbox_api.INBOX_MESSAGE_ERROR_MESSAGE)
        return HttpResponseRedirect(list_url)
    except Exception:
        inbox_api.logger.exception("Unexpected error fetching message uid=%s.", uid)
        messages.error(request, inbox_api.INBOX_MESSAGE_ERROR_MESSAGE)
        return HttpResponseRedirect(list_url)

    body_html = message_body_html(msg)
    scam_analysis = inbox_api.assess_email(msg, folder=folder)

    context = {
        **admin.site.each_context(request),
        "title": f"Message: {msg['subject']}",
        "msg": msg,
        "body_html_json": safe_json(body_html),
        "reply_url": reverse("admin:mail_inbox_reply", args=[uid]),
        "list_url": list_url,
        "scam_analysis": scam_analysis,
        "folder": folder,
    }
    return TemplateResponse(request, "admin/mail/inbox/detail.html", context)


def inbox_detail_fragment_view(request, uid):
    """Return HTML partial for the message preview pane."""
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access the mail inbox.")
    folder = parse_folder(request)
    try:
        msg = inbox_api.fetch_inbox_message(uid, folder=folder)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox message uid=%s could not be loaded: %s", uid, exc)
        return HttpResponse(
            f'<div class="p-4 text-sm text-red-600">{inbox_api.INBOX_MESSAGE_ERROR_MESSAGE}</div>',
            status=200,
        )
    except Exception:
        inbox_api.logger.exception("Unexpected error fetching message uid=%s.", uid)
        return HttpResponse(
            f'<div class="p-4 text-sm text-red-600">{inbox_api.INBOX_MESSAGE_ERROR_MESSAGE}</div>',
            status=200,
        )

    body_html = message_body_html(msg)
    scam_analysis = inbox_api.assess_email(msg, folder=folder)
    html = render_to_string(
        "admin/mail/inbox/_inbox_preview.html",
        {
            "msg": msg,
            "body_html_json": safe_json(body_html),
            "reply_url": reverse("admin:mail_inbox_reply", args=[uid]),
            "reply_fragment_url": reverse("admin:mail_inbox_reply_fragment", args=[uid]),
            "scam_analysis": scam_analysis,
            "folder": folder,
        },
        request=request,
    )
    return HttpResponse(html)
