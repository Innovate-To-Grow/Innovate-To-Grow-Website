"""Inbox detail admin views."""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.core.utils.access import user_can_access_app
from apps.core.utils.json_helpers import safe_json

from . import services as inbox_api
from .helpers import (
    message_body_html,
    message_load_error,
    parse_account,
    parse_folder,
    with_query,
)


def inbox_detail_view(request, uid):
    """Display a single inbox message."""
    # A plain Admin check, in case the URL is ever mounted without ``admin_view``.
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access the mail inbox.")
    list_url = reverse("admin:mail_inbox_list")
    folder = parse_folder(request)
    account = parse_account(request)

    try:
        msg = inbox_api.fetch_inbox_message(uid, folder=folder, account=account)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox message uid=%s could not be loaded: %s", uid, exc)
        messages.error(request, message_load_error(exc))
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
        "reply_url": with_query(reverse("admin:mail_inbox_reply", args=[uid]), account=account),
        "list_url": list_url,
        "scam_analysis": scam_analysis,
        "folder": folder,
    }
    return TemplateResponse(request, "admin/mail/inbox/detail/detail.html", context)


def inbox_detail_fragment_view(request, uid):
    """Return HTML partial for the message preview pane."""
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access the mail inbox.")
    folder = parse_folder(request)
    account = parse_account(request)
    try:
        msg = inbox_api.fetch_inbox_message(uid, folder=folder, account=account)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox message uid=%s could not be loaded: %s", uid, exc)
        return TemplateResponse(
            request,
            "admin/mail/inbox/shared/_fragment_error.html",
            {"error_message": message_load_error(exc)},
        )
    except Exception:
        inbox_api.logger.exception("Unexpected error fetching message uid=%s.", uid)
        return TemplateResponse(
            request,
            "admin/mail/inbox/shared/_fragment_error.html",
            {"error_message": inbox_api.INBOX_MESSAGE_ERROR_MESSAGE},
        )

    body_html = message_body_html(msg)
    scam_analysis = inbox_api.assess_email(msg, folder=folder)
    return TemplateResponse(
        request,
        "admin/mail/inbox/detail/_inbox_preview.html",
        {
            "msg": msg,
            "body_html_json": safe_json(body_html),
            "reply_url": with_query(reverse("admin:mail_inbox_reply", args=[uid]), account=account),
            "reply_fragment_url": with_query(reverse("admin:mail_inbox_reply_fragment", args=[uid]), account=account),
            "scam_analysis": scam_analysis,
            "folder": folder,
        },
    )
