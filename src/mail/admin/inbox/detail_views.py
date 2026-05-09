"""Inbox detail admin views."""

import json

from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import reverse

import mail.admin.inbox as inbox_api

from .helpers import message_body_html


def inbox_detail_view(request, uid):
    """Display a single inbox message."""
    list_url = reverse("admin:mail_inbox_list")

    try:
        msg = inbox_api.fetch_inbox_message(uid)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox message uid=%s could not be loaded: %s", uid, exc)
        messages.error(request, inbox_api.INBOX_MESSAGE_ERROR_MESSAGE)
        return HttpResponseRedirect(list_url)
    except Exception:
        inbox_api.logger.exception("Unexpected error fetching message uid=%s.", uid)
        messages.error(request, inbox_api.INBOX_MESSAGE_ERROR_MESSAGE)
        return HttpResponseRedirect(list_url)

    body_html = message_body_html(msg)
    scam_analysis = inbox_api.analyze_email(msg)

    context = {
        **admin.site.each_context(request),
        "title": f"Message: {msg['subject']}",
        "msg": msg,
        "body_html_json": json.dumps(body_html),
        "reply_url": reverse("admin:mail_inbox_reply", args=[uid]),
        "list_url": list_url,
        "scam_analysis": scam_analysis,
    }
    return TemplateResponse(request, "admin/mail/inbox/detail.html", context)


def inbox_detail_fragment_view(request, uid):
    """Return HTML partial for the message preview pane."""
    try:
        msg = inbox_api.fetch_inbox_message(uid)
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
    scam_analysis = inbox_api.analyze_email(msg)
    html = render_to_string(
        "admin/mail/inbox/_inbox_preview.html",
        {
            "msg": msg,
            "body_html_json": json.dumps(body_html),
            "reply_url": reverse("admin:mail_inbox_reply", args=[uid]),
            "reply_fragment_url": reverse("admin:mail_inbox_reply_fragment", args=[uid]),
            "scam_analysis": scam_analysis,
        },
        request=request,
    )
    return HttpResponse(html)
