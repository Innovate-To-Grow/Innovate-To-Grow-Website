"""Admin views for Gmail inbox viewer and reply functionality."""

import json
import logging

from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import path, reverse

from core.models import EmailServiceConfig, GmailImportConfig

from ..services.inbox import INBOX_LIMIT_CHOICES, InboxError, fetch_inbox_message, list_inbox_messages, send_reply

logger = logging.getLogger(__name__)


def get_inbox_urls():
    """Return URL patterns for the inbox admin views."""
    return [
        path(
            "mail/inbox/",
            admin.site.admin_view(inbox_list_view),
            name="mail_inbox_list",
        ),
        path(
            "mail/inbox/fragment/",
            admin.site.admin_view(inbox_fragment_view),
            name="mail_inbox_fragment",
        ),
        path(
            "mail/inbox/<str:uid>/",
            admin.site.admin_view(inbox_detail_view),
            name="mail_inbox_detail",
        ),
        path(
            "mail/inbox/<str:uid>/fragment/",
            admin.site.admin_view(inbox_detail_fragment_view),
            name="mail_inbox_detail_fragment",
        ),
        path(
            "mail/inbox/<str:uid>/reply/",
            admin.site.admin_view(inbox_reply_view),
            name="mail_inbox_reply",
        ),
        path(
            "mail/inbox/<str:uid>/reply/fragment/",
            admin.site.admin_view(inbox_reply_fragment_view),
            name="mail_inbox_reply_fragment",
        ),
    ]


INBOX_DEFAULT_LIMIT = 30


def _parse_limit(request) -> int:
    try:
        value = int(request.GET.get("limit", INBOX_DEFAULT_LIMIT))
    except (TypeError, ValueError):
        return INBOX_DEFAULT_LIMIT
    return value if value in INBOX_LIMIT_CHOICES else INBOX_DEFAULT_LIMIT


def inbox_list_view(request):
    """Render the inbox shell instantly; JS fetches content asynchronously."""
    context = {
        **admin.site.each_context(request),
        "title": "Inbox",
        "fragment_url": reverse("admin:mail_inbox_fragment"),
    }
    return TemplateResponse(request, "admin/mail/inbox/list.html", context)


def inbox_fragment_view(request):
    """Return HTML partial for inbox list + config stats (AJAX)."""
    gmail_config = GmailImportConfig.load()
    error_message = ""
    inbox_messages = []
    limit = _parse_limit(request)
    force_refresh = request.GET.get("refresh") == "1"

    try:
        inbox_messages = list_inbox_messages(limit=limit, force_refresh=force_refresh)
    except InboxError as exc:
        error_message = str(exc)
    except Exception as exc:
        logger.exception("Unexpected error refreshing inbox fragment.")
        error_message = f"Unexpected error: {exc}"

    html = render_to_string(
        "admin/mail/inbox/_inbox_full_body.html",
        {
            "gmail_config": gmail_config,
            "inbox_messages": inbox_messages,
            "error_message": error_message,
            "limit": limit,
            "limit_choices": INBOX_LIMIT_CHOICES,
        },
        request=request,
    )
    return HttpResponse(html)


def inbox_detail_view(request, uid):
    """Display a single inbox message."""
    list_url = reverse("admin:mail_inbox_list")

    try:
        msg = fetch_inbox_message(uid)
    except InboxError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(list_url)
    except Exception as exc:
        logger.exception("Unexpected error fetching message uid=%s.", uid)
        messages.error(request, f"Unexpected error: {exc}")
        return HttpResponseRedirect(list_url)

    body_html = msg["html"] or f"<pre>{msg['text']}</pre>"

    context = {
        **admin.site.each_context(request),
        "title": f"Message: {msg['subject']}",
        "msg": msg,
        "body_html_json": json.dumps(body_html),
        "reply_url": reverse("admin:mail_inbox_reply", args=[uid]),
        "list_url": list_url,
    }
    return TemplateResponse(request, "admin/mail/inbox/detail.html", context)


def inbox_detail_fragment_view(request, uid):
    """Return HTML partial for the message preview pane (AJAX)."""
    try:
        msg = fetch_inbox_message(uid)
    except InboxError as exc:
        return HttpResponse(
            f'<div class="p-4 text-sm text-red-600">{exc}</div>',
            status=200,
        )
    except Exception as exc:
        logger.exception("Unexpected error fetching message uid=%s.", uid)
        return HttpResponse(
            f'<div class="p-4 text-sm text-red-600">Unexpected error: {exc}</div>',
            status=200,
        )

    body_html = msg["html"] or f"<pre>{msg['text']}</pre>"

    html = render_to_string(
        "admin/mail/inbox/_inbox_preview.html",
        {
            "msg": msg,
            "body_html_json": json.dumps(body_html),
            "reply_url": reverse("admin:mail_inbox_reply", args=[uid]),
            "reply_fragment_url": reverse("admin:mail_inbox_reply_fragment", args=[uid]),
        },
        request=request,
    )
    return HttpResponse(html)


def inbox_reply_view(request, uid):
    """Compose and send a reply to an inbox message."""
    list_url = reverse("admin:mail_inbox_list")
    detail_url = reverse("admin:mail_inbox_detail", args=[uid])

    try:
        msg = fetch_inbox_message(uid)
    except InboxError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(list_url)

    email_config = EmailServiceConfig.load()
    original_subject = msg["subject"]
    reply_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"

    # Build references for threading
    reply_references = msg.get("references", "")
    if msg.get("message_id"):
        if reply_references:
            reply_references = f"{reply_references} {msg['message_id']}"
        else:
            reply_references = msg["message_id"]

    # Build original sender display for quoting
    original_from = msg["from_name"] or msg["from_email"]
    if msg["from_name"]:
        original_from = f"{msg['from_name']} <{msg['from_email']}>"

    if request.method == "POST":
        reply_body = request.POST.get("reply_body", "").strip()
        subject = request.POST.get("subject", reply_subject).strip()
        to_email = request.POST.get("to_email", msg["from_email"]).strip()
        cc_email = request.POST.get("cc_email", "").strip()

        if not reply_body:
            messages.error(request, "Reply body cannot be empty.")
            return HttpResponseRedirect(request.path)

        error = send_reply(
            to_email=to_email,
            subject=subject,
            reply_body=reply_body,
            in_reply_to=msg.get("message_id", ""),
            references=reply_references,
            original_from=original_from,
            original_date=msg.get("date", ""),
            quoted_text=msg.get("text", ""),
            cc_email=cc_email,
        )

        if error:
            messages.error(request, f"Failed to send reply: {error}")
            return HttpResponseRedirect(request.path)

        messages.success(request, f"Reply sent to {to_email}.")
        return HttpResponseRedirect(detail_url)

    context = {
        **admin.site.each_context(request),
        "title": f"Reply: {original_subject}",
        "msg": msg,
        "reply_subject": reply_subject,
        "from_address": email_config.source_address,
        "detail_url": detail_url,
        "list_url": list_url,
    }
    return TemplateResponse(request, "admin/mail/inbox/reply.html", context)


def inbox_reply_fragment_view(request, uid):
    """AJAX reply: GET returns form HTML, POST sends the reply and returns JSON."""
    try:
        msg = fetch_inbox_message(uid)
    except (InboxError, Exception) as exc:
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": str(exc)})
        return HttpResponse(f'<div class="p-4 text-sm text-red-600">{exc}</div>')

    email_config = EmailServiceConfig.load()
    original_subject = msg["subject"]
    reply_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"

    if request.method == "POST":
        reply_body = request.POST.get("reply_body", "").strip()
        subject = request.POST.get("subject", reply_subject).strip()
        to_email = request.POST.get("to_email", msg["from_email"]).strip()

        if not reply_body:
            return JsonResponse({"ok": False, "error": "Reply body cannot be empty."})

        reply_references = msg.get("references", "")
        if msg.get("message_id"):
            reply_references = f"{reply_references} {msg['message_id']}".strip()

        original_from = msg["from_name"] or msg["from_email"]
        if msg["from_name"]:
            original_from = f"{msg['from_name']} <{msg['from_email']}>"

        cc_email = request.POST.get("cc_email", "").strip()

        error = send_reply(
            to_email=to_email,
            subject=subject,
            reply_body=reply_body,
            in_reply_to=msg.get("message_id", ""),
            references=reply_references,
            original_from=original_from,
            original_date=msg.get("date", ""),
            quoted_text=msg.get("text", ""),
            cc_email=cc_email,
        )

        if error:
            return JsonResponse({"ok": False, "error": f"Failed to send: {error}"})
        sent_to = to_email
        if cc_email:
            sent_to += f" (Cc: {cc_email})"
        return JsonResponse({"ok": True, "message": f"Reply sent to {sent_to}."})

    # GET — render the reply form partial
    html = render_to_string(
        "admin/mail/inbox/_inbox_reply_form.html",
        {
            "msg": msg,
            "reply_subject": reply_subject,
            "from_address": email_config.source_address,
            "reply_fragment_url": reverse("admin:mail_inbox_reply_fragment", args=[uid]),
        },
        request=request,
    )
    return HttpResponse(html)
