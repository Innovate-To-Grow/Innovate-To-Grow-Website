"""Inbox reply admin views."""

from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import reverse

import mail.admin.inbox as inbox_api
from core.models import EmailServiceConfig

from .helpers import build_original_from, build_reply_references, build_reply_subject


def inbox_reply_view(request, uid):
    """Compose and send a reply to an inbox message."""
    list_url = reverse("admin:mail_inbox_list")
    detail_url = reverse("admin:mail_inbox_detail", args=[uid])

    try:
        msg = inbox_api.fetch_inbox_message(uid)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox message uid=%s could not be loaded for reply: %s", uid, exc)
        messages.error(request, inbox_api.INBOX_MESSAGE_ERROR_MESSAGE)
        return HttpResponseRedirect(list_url)

    email_config = EmailServiceConfig.load()
    original_subject = msg["subject"]
    reply_subject = build_reply_subject(original_subject)
    reply_references = build_reply_references(msg)
    original_from = build_original_from(msg)

    if request.method == "POST":
        reply_body = request.POST.get("reply_body", "").strip()
        subject = request.POST.get("subject", reply_subject).strip()
        to_email = request.POST.get("to_email", msg["from_email"]).strip()
        cc_email = request.POST.get("cc_email", "").strip()

        if not reply_body:
            messages.error(request, "Reply body cannot be empty.")
            return HttpResponseRedirect(request.path)

        error = inbox_api.send_reply(
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
            messages.error(request, error)
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
    """AJAX reply: GET returns form HTML, POST sends and returns JSON."""
    try:
        msg = inbox_api.fetch_inbox_message(uid)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox message uid=%s could not be loaded for reply fragment: %s", uid, exc)
        return _reply_load_error_response(request)
    except Exception:
        inbox_api.logger.exception("Unexpected error loading reply fragment uid=%s.", uid)
        return _reply_load_error_response(request)

    email_config = EmailServiceConfig.load()
    reply_subject = build_reply_subject(msg["subject"])

    if request.method == "POST":
        return _send_reply_fragment(request, msg, reply_subject)

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


def _send_reply_fragment(request, msg, reply_subject):
    reply_body = request.POST.get("reply_body", "").strip()
    subject = request.POST.get("subject", reply_subject).strip()
    to_email = request.POST.get("to_email", msg["from_email"]).strip()
    cc_email = request.POST.get("cc_email", "").strip()

    if not reply_body:
        return JsonResponse({"ok": False, "error": "Reply body cannot be empty."})

    error = inbox_api.send_reply(
        to_email=to_email,
        subject=subject,
        reply_body=reply_body,
        in_reply_to=msg.get("message_id", ""),
        references=build_reply_references(msg),
        original_from=build_original_from(msg),
        original_date=msg.get("date", ""),
        quoted_text=msg.get("text", ""),
        cc_email=cc_email,
    )

    if error:
        return JsonResponse({"ok": False, "error": error})

    sent_to = to_email
    if cc_email:
        sent_to += f" (Cc: {cc_email})"
    return JsonResponse({"ok": True, "message": f"Reply sent to {sent_to}."})


def _reply_load_error_response(request):
    if request.method == "POST":
        return JsonResponse({"ok": False, "error": inbox_api.INBOX_MESSAGE_ERROR_MESSAGE})
    return HttpResponse(f'<div class="p-4 text-sm text-red-600">{inbox_api.INBOX_MESSAGE_ERROR_MESSAGE}</div>')
