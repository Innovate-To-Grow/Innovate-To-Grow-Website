from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from authn.models import Member
from authn.services.unsubscribe_token import build_unsubscribe_url
from mail.forms import ComposeForm
from mail.models import EmailLog, SESAccount, SESEmailLog
from mail.services.email_layout import get_logo_data_uri, get_logo_inline_image, render_email_layout
from mail.services.recipients import personalize_body, resolve_recipients


def get_active_account(request):
    account = SESAccount.get_active()
    if not account:
        messages.error(request, "No active SES sender is configured. Re-enable the existing SES Mail Sender first.")
        return None
    return account


def build_compose_context(admin_obj, request, form, account):
    subscriber_count = Member.objects.filter(email_subscribe=True, is_active=True).count()
    return {
        **admin_obj.admin_site.each_context(request),
        "title": "Compose SES Email",
        "opts": admin_obj.model._meta,
        "form": form,
        "account_email": account.email,
        "send_url": reverse("admin:mail_ses_send"),
        "preview_url": reverse("admin:mail_ses_preview"),
        "cancel_url": reverse("admin:mail_sesaccount_changelist"),
        "parent_label": "SES Mail Senders",
        "parent_url": reverse("admin:mail_sesaccount_changelist"),
        "subscriber_count": subscriber_count,
        "show_recipient_settings": True,
    }


def log_action(account, status, request, message_id="", subject="", recipients="", error=""):
    common = {
        "subject": subject[:500] if subject else "",
        "recipients": recipients,
        "error_message": error,
        "performed_by": request.user if request.user.is_authenticated else None,
    }
    SESEmailLog.objects.create(
        account=account, action=SESEmailLog.Action.SEND, status=status, ses_message_id=message_id, **common
    )
    EmailLog.objects.create(
        account=None, action=EmailLog.Action.SEND, status=status, gmail_message_id=message_id, **common
    )


def compose_view(admin_obj, request):
    account = get_active_account(request)
    if not account:
        return redirect(reverse("admin:mail_sesaccount_changelist"))
    return render(request, "admin/mail/compose.html", build_compose_context(admin_obj, request, ComposeForm(), account))


def preview_action(request):
    if request.method != "POST":
        return redirect(reverse("admin:mail_ses_compose"))
    body = request.POST.get("body", "").replace("{name}", "Hongzhe")
    unsub_url = "#unsubscribe-preview" if request.POST.get("include_unsubscribe_link") == "on" else ""
    preview_html = render_email_layout(body, logo_src=get_logo_data_uri(), unsubscribe_url=unsub_url)
    page_html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Email Preview</title></head>'
        '<body style="margin:0;padding:40px 20px;background:#f3f4f6;font-family:Arial,sans-serif;">'
        f"{preview_html}</body></html>"
    )
    return HttpResponse(page_html, content_type="text/html")


def send_manual(request, account, data, attachments, ses_service_cls, ses_error_cls):
    try:
        result = ses_service_cls(account).send_message(
            to=data["to"],
            subject=data["subject"],
            body_html=render_email_layout(data["body"]),
            cc=data.get("cc", ""),
            bcc=data.get("bcc", ""),
            attachments=attachments or None,
            inline_images=[get_logo_inline_image()],
        )
        log_action(
            account,
            SESEmailLog.Status.SUCCESS,
            request,
            message_id=result["id"],
            subject=data["subject"],
            recipients=data["to"],
        )
        account.mark_used()
        messages.success(request, f"SES email sent successfully to {data['to']}")
    except ses_error_cls as exc:
        log_action(
            account, SESEmailLog.Status.FAILED, request, subject=data["subject"], recipients=data["to"], error=str(exc)
        )
        account.mark_used(error=str(exc))
        messages.error(request, f"Failed to send SES email: {exc}")


def send_personalized(request, account, data, ses_service_cls, ses_error_cls, logger):
    results, service = [], ses_service_cls(account)
    for recipient in resolve_recipients(data["recipient_source"], data.get("event")):
        unsub_url = ""
        if data.get("include_unsubscribe_link", False):
            try:
                unsub_url = build_unsubscribe_url(Member.objects.get(pk=recipient["member_id"]))
            except Member.DoesNotExist:
                pass
        try:
            result = service.send_message(
                to=recipient["email"],
                subject=data["subject"],
                body_html=render_email_layout(personalize_body(data["body"], recipient), unsubscribe_url=unsub_url),
                attachments=[],
                inline_images=[get_logo_inline_image()],
            )
            log_action(
                account,
                SESEmailLog.Status.SUCCESS,
                request,
                message_id=result["id"],
                subject=data["subject"],
                recipients=recipient["email"],
            )
            results.append(
                {"email": recipient["email"], "name": recipient["full_name"], "status": "success", "error": ""}
            )
            logger.info("SES email sent to %s (message_id=%s)", recipient["email"], result["id"])
        except ses_error_cls as exc:
            log_action(
                account,
                SESEmailLog.Status.FAILED,
                request,
                subject=data["subject"],
                recipients=recipient["email"],
                error=str(exc),
            )
            results.append(
                {"email": recipient["email"], "name": recipient["full_name"], "status": "failed", "error": str(exc)}
            )
            logger.exception("SES email failed for %s", recipient["email"])
    account.mark_used()
    return results
