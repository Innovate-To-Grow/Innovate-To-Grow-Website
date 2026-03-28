import mimetypes
import re

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from mail.forms import ComposeForm
from mail.models import EmailLog

from .actions import get_gmail_service, log_action


def build_compose_context(
    admin_obj, request, form, account, *, title, compose_mode, cancel_url, original_message_id=""
):
    return {
        **admin_obj.admin_site.each_context(request),
        "title": title,
        "opts": admin_obj.model._meta,
        "form": form,
        "compose_mode": compose_mode,
        "original_message_id": original_message_id,
        "account_email": account.email,
        "send_url": reverse("admin:mail_send"),
        "cancel_url": cancel_url,
        "parent_label": "Inbox",
        "parent_url": reverse("admin:mail_inbox"),
    }


def render_mailbox_view(admin_obj, request, gmail_service_cls, error_cls, *, label_ids, title, current_view):
    service, account = get_gmail_service(request, gmail_service_cls)
    if not service:
        return redirect(reverse("admin:mail_googleaccount_changelist"))
    q = request.GET.get("q", "")
    page_token = request.GET.get("page_token", "") or None
    try:
        result = service.list_messages(q=q, label_ids=label_ids, max_results=25, page_token=page_token)
    except error_cls as exc:
        messages.error(request, f"Failed to load {current_view}: {exc}")
        account.mark_used(error=str(exc))
        result = {"messages": [], "next_page_token": None}
    return render(
        request,
        "admin/mail/inbox.html",
        {
            **admin_obj.admin_site.each_context(request),
            "title": title,
            "opts": admin_obj.model._meta,
            "messages_list": result["messages"],
            "next_page_token": result["next_page_token"],
            "search_query": q,
            "current_view": current_view,
            "account_email": account.email,
        },
    )


def message_detail_view(admin_obj, request, message_id, gmail_service_cls, error_cls):
    service, account = get_gmail_service(request, gmail_service_cls)
    if not service:
        return redirect(reverse("admin:mail_googleaccount_changelist"))
    try:
        msg = service.get_message(message_id)
        if msg["is_unread"]:
            service.modify_labels(message_id, remove_labels=["UNREAD"])
        log_action(
            account,
            EmailLog.Action.READ,
            EmailLog.Status.SUCCESS,
            request,
            message_id=message_id,
            subject=msg["subject"],
        )
    except error_cls as exc:
        messages.error(request, f"Failed to load message: {exc}")
        account.mark_used(error=str(exc))
        return redirect(reverse("admin:mail_inbox"))
    return render(
        request,
        "admin/mail/message_detail.html",
        {
            **admin_obj.admin_site.each_context(request),
            "title": msg["subject"] or "(no subject)",
            "opts": admin_obj.model._meta,
            "msg": msg,
        },
    )


def compose_view(admin_obj, request, gmail_service_cls):
    service, account = get_gmail_service(request, gmail_service_cls)
    if not service:
        return redirect(reverse("admin:mail_googleaccount_changelist"))
    context = build_compose_context(
        admin_obj,
        request,
        ComposeForm(),
        account,
        title="Compose Email",
        compose_mode="compose",
        cancel_url=reverse("admin:mail_inbox"),
    )
    return render(request, "admin/mail/compose.html", context)


def reply_or_forward_view(admin_obj, request, message_id, gmail_service_cls, error_cls, *, mode):
    service, account = get_gmail_service(request, gmail_service_cls)
    if not service:
        return redirect(reverse("admin:mail_googleaccount_changelist"))
    try:
        msg = service.get_message(message_id)
    except error_cls as exc:
        messages.error(request, f"Failed to load message for {mode}: {exc}")
        return redirect(reverse("admin:mail_inbox"))

    subject_prefix = "Re:" if mode == "reply" else "Fwd:"
    subject = (
        msg["subject"]
        if msg["subject"].lower().startswith(subject_prefix.lower())
        else f"{subject_prefix} {msg['subject']}"
    )
    initial = {"subject": subject, "thread_id": msg["thread_id"]}
    if mode == "reply":
        initial.update(
            {
                "to": msg["from"],
                "body": f'<br><br><div style="border-left: 2px solid #ccc; padding-left: 10px; margin-left: 5px; color: #666;">On {msg["date"]}, {msg["from"]} wrote:<br>{msg["body_html"] or msg["body_plain"]}</div>',
                "in_reply_to": msg["message_id"],
                "references": f"{msg.get('references', '')} {msg['message_id']}".strip(),
            }
        )
    else:
        initial["body"] = (
            f"<br><br>---------- Forwarded message ----------<br>From: {msg['from']}<br>Date: {msg['date']}<br>"
            f"Subject: {msg['subject']}<br>To: {msg['to']}<br><br>{msg['body_html'] or msg['body_plain']}"
        )

    context = build_compose_context(
        admin_obj,
        request,
        ComposeForm(initial=initial),
        account,
        title=f"{'Reply' if mode == 'reply' else 'Forward'}: {msg['subject']}",
        compose_mode=mode,
        cancel_url=reverse("admin:mail_inbox"),
        original_message_id=message_id,
    )
    return render(request, "admin/mail/compose.html", context)


def send_action(admin_obj, request, gmail_service_cls, error_cls):
    if request.method != "POST":
        return redirect(reverse("admin:mail_compose"))
    service, account = get_gmail_service(request, gmail_service_cls)
    if not service:
        return redirect(reverse("admin:mail_googleaccount_changelist"))

    form = ComposeForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            "admin/mail/compose.html",
            build_compose_context(
                admin_obj,
                request,
                form,
                account,
                title="Compose Email",
                compose_mode="compose",
                cancel_url=reverse("admin:mail_inbox"),
            ),
        )

    data = form.cleaned_data
    action = (
        EmailLog.Action.REPLY
        if data.get("in_reply_to")
        else EmailLog.Action.FORWARD
        if data.get("thread_id")
        else EmailLog.Action.SEND
    )
    attachments = [(uploaded.name, uploaded.read()) for uploaded in request.FILES.getlist("attachments")]
    try:
        result = service.send_message(
            to=data["to"],
            subject=data["subject"],
            body_html=data["body"],
            cc=data.get("cc", ""),
            bcc=data.get("bcc", ""),
            attachments=attachments or None,
            thread_id=data.get("thread_id") or None,
            in_reply_to=data.get("in_reply_to") or None,
            references=data.get("references") or None,
        )
        log_action(
            account,
            action,
            EmailLog.Status.SUCCESS,
            request,
            message_id=result["id"],
            subject=data["subject"],
            recipients=data["to"],
        )
        account.mark_used()
        messages.success(request, f"Email sent successfully to {data['to']}")
    except error_cls as exc:
        log_action(
            account,
            action,
            EmailLog.Status.FAILED,
            request,
            subject=data["subject"],
            recipients=data["to"],
            error=str(exc),
        )
        account.mark_used(error=str(exc))
        messages.error(request, f"Failed to send email: {exc}")
    return redirect(reverse("admin:mail_inbox"))


def message_operation_view(admin_obj, request, message_id, gmail_service_cls, error_cls, *, op):
    if request.method != "POST" and op != "attachment":
        return redirect(reverse("admin:mail_inbox"))
    service, account = get_gmail_service(request, gmail_service_cls)
    if not service:
        return redirect(reverse("admin:mail_googleaccount_changelist"))
    if op == "attachment":
        try:
            filename, data = service.get_attachment(message_id, request.resolver_match.kwargs["attachment_id"])
            safe_filename = re.sub(r'["\r\n/\\]', "_", filename)
            response = HttpResponse(
                data, content_type=mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
            )
            response["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
            return response
        except error_cls as exc:
            messages.error(request, f"Failed to download attachment: {exc}")
            return redirect(reverse("admin:mail_message_detail", args=[message_id]))

    add_labels = request.POST.getlist("add_labels")
    remove_labels = request.POST.getlist("remove_labels")
    action = EmailLog.Action.DELETE if op == "trash" else EmailLog.Action.LABEL
    success_message = "Message moved to trash." if op == "trash" else "Labels updated."
    error_message = "Failed to trash message" if op == "trash" else "Failed to update labels"
    try:
        if op == "trash":
            service.trash_message(message_id)
        else:
            service.modify_labels(message_id, add_labels=add_labels or None, remove_labels=remove_labels or None)
        log_action(account, action, EmailLog.Status.SUCCESS, request, message_id=message_id)
        messages.success(request, success_message)
    except error_cls as exc:
        log_action(account, action, EmailLog.Status.FAILED, request, message_id=message_id, error=str(exc))
        messages.error(request, f"{error_message}: {exc}")
    return redirect(
        reverse(
            "admin:mail_inbox" if op == "trash" else "admin:mail_message_detail",
            args=[] if op == "trash" else [message_id],
        )
    )
