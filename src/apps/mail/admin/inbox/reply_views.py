"""Inbox reply admin views.

A reply may be sent From any configured sending address (``apps.mail.services.inbox.senders``); the form starts
with the address the message was received at when the site can send as it.
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.core.models import EmailServiceConfig
from apps.core.utils.access import user_can_access_app

from . import services as inbox_api
from .detail_views import sent_mail_denied_fragment
from .helpers import (
    build_original_from,
    build_reply_references,
    build_reply_subject,
    message_load_error,
    parse_account,
    sent_mail_denied,
    with_query,
)


def _sender_context(msg) -> dict:
    """The From choices of the reply form, and the one it starts with."""
    try:
        identities = inbox_api.send_identities()
    except Exception:
        inbox_api.logger.exception("Could not list the reply senders.")
        identities = []
    selected = inbox_api.default_identity_for(identities, msg.get("account_address", ""))
    return {
        "senders": identities,
        "selected_sender": selected.key if selected else inbox_api.DEFAULT_SENDER,
        "from_address": selected.label if selected else EmailServiceConfig.load().source_address,
    }


def _reply_fields(request, msg, reply_subject) -> dict:
    return {
        "reply_body": request.POST.get("reply_body", "").strip(),
        "subject": request.POST.get("subject", reply_subject).strip(),
        "to_email": request.POST.get("to_email", msg["from_email"]).strip(),
        "cc_email": request.POST.get("cc_email", "").strip(),
        "sender": request.POST.get("sender", inbox_api.DEFAULT_SENDER).strip() or inbox_api.DEFAULT_SENDER,
    }


def _send(msg, fields) -> str:
    return inbox_api.send_reply(
        to_email=fields["to_email"],
        subject=fields["subject"],
        reply_body=fields["reply_body"],
        in_reply_to=msg.get("message_id", ""),
        references=build_reply_references(msg),
        original_from=build_original_from(msg),
        original_date=msg.get("date", ""),
        quoted_text=msg.get("text", ""),
        cc_email=fields["cc_email"],
        sender=fields["sender"],
    )


def _send_reply_from_post(request, msg, *, reply_subject, reply_url, detail_url):
    fields = _reply_fields(request, msg, reply_subject)
    if not fields["reply_body"]:
        messages.error(request, "Reply body cannot be empty.")
        return HttpResponseRedirect(reply_url)

    error = _send(msg, fields)
    if error:
        messages.error(request, error)
        return HttpResponseRedirect(reply_url)

    messages.success(request, f"Reply sent to {fields['to_email']}.")
    return HttpResponseRedirect(detail_url)


def inbox_reply_view(request, uid):
    """Compose and send a reply to an inbox message."""
    # ``admin_view`` only enforces is_staff, so this custom URL must re-check
    # per-app access itself. This can send mail on POST.
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to reply from the mail inbox.")
    account = parse_account(request)
    list_url = reverse("admin:mail_inbox_list")
    detail_url = with_query(reverse("admin:mail_inbox_detail", args=[uid]), account=account)
    reply_url = with_query(reverse("admin:mail_inbox_reply", args=[uid]), account=account)

    try:
        msg = inbox_api.fetch_inbox_message(uid, account=account)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox message uid=%s could not be loaded for reply: %s", uid, exc)
        messages.error(request, message_load_error(exc))
        return HttpResponseRedirect(list_url)
    # A reply quotes the original, so replying to Sent mail would disclose it like opening it.
    if sent_mail_denied(request, inbox_api.INBOX_FOLDER, msg):
        raise PermissionDenied(inbox_api.SENT_MAIL_DENIED_MESSAGE)

    original_subject = msg["subject"]
    reply_subject = build_reply_subject(original_subject)

    if request.method == "POST":
        return _send_reply_from_post(
            request, msg, reply_subject=reply_subject, reply_url=reply_url, detail_url=detail_url
        )

    context = {
        **admin.site.each_context(request),
        "title": f"Reply: {original_subject}",
        "msg": msg,
        "reply_subject": reply_subject,
        **_sender_context(msg),
        "detail_url": detail_url,
        "list_url": list_url,
    }
    return TemplateResponse(request, "admin/mail/inbox/reply/reply.html", context)


def inbox_reply_fragment_view(request, uid):
    """AJAX reply: GET returns form HTML, POST sends and returns JSON."""
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to reply from the mail inbox.")
    account = parse_account(request)
    try:
        msg = inbox_api.fetch_inbox_message(uid, account=account)
    except inbox_api.InboxError as exc:
        inbox_api.logger.warning("Inbox message uid=%s could not be loaded for reply fragment: %s", uid, exc)
        return _reply_load_error_response(request, message_load_error(exc))
    except Exception:
        inbox_api.logger.exception("Unexpected error loading reply fragment uid=%s.", uid)
        return _reply_load_error_response(request)
    if sent_mail_denied(request, inbox_api.INBOX_FOLDER, msg):
        if request.method == "POST":
            return JsonResponse({"ok": False, "error": inbox_api.SENT_MAIL_DENIED_MESSAGE}, status=403)
        return sent_mail_denied_fragment(request)

    reply_subject = build_reply_subject(msg["subject"])

    if request.method == "POST":
        return _send_reply_fragment(request, msg, reply_subject)

    return TemplateResponse(
        request,
        "admin/mail/inbox/reply/_inbox_reply_form.html",
        {
            "msg": msg,
            "reply_subject": reply_subject,
            **_sender_context(msg),
            "reply_fragment_url": with_query(reverse("admin:mail_inbox_reply_fragment", args=[uid]), account=account),
        },
    )


def _send_reply_fragment(request, msg, reply_subject):
    fields = _reply_fields(request, msg, reply_subject)
    if not fields["reply_body"]:
        return JsonResponse({"ok": False, "error": "Reply body cannot be empty."})

    error = _send(msg, fields)
    if error:
        return JsonResponse({"ok": False, "error": error})

    sent_to = fields["to_email"]
    if fields["cc_email"]:
        sent_to += f" (Cc: {fields['cc_email']})"
    return JsonResponse({"ok": True, "message": f"Reply sent to {sent_to}."})


def _reply_load_error_response(request, error=None):
    error = error or inbox_api.INBOX_MESSAGE_ERROR_MESSAGE
    if request.method == "POST":
        return JsonResponse({"ok": False, "error": error})
    return TemplateResponse(request, "admin/mail/inbox/shared/_fragment_error.html", {"error_message": error})
