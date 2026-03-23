"""
Admin configuration for the SES sender with a dedicated compose flow.
"""

import logging

from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from authn.models import Member
from authn.services.unsubscribe_token import build_unsubscribe_url
from core.admin.base import BaseModelAdmin
from mail.forms import ComposeForm
from mail.models import EmailLog, SESAccount, SESEmailLog
from mail.services.email_layout import get_logo_data_uri, get_logo_inline_image, render_email_layout
from mail.services.recipients import personalize_body, resolve_recipients
from mail.services.ses import SESService, SESServiceError

logger = logging.getLogger(__name__)


@admin.register(SESAccount)
class SESAccountAdmin(BaseModelAdmin):
    """Admin for the dedicated SES sender used by the new I2G system."""

    change_list_template = "admin/mail/sesaccount/change_list.html"
    list_display = (
        "email",
        "display_name",
        "is_active_badge",
        "compose_link",
        "last_used_at",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("email", "display_name")
    readonly_fields = ("id", "email", "last_used_at", "last_error", "created_at", "updated_at")
    fields = ("email", "display_name", "is_active", "last_used_at", "last_error", "created_at", "updated_at")

    @admin.display(description="Active", boolean=True, ordering="is_active")
    def is_active_badge(self, obj):
        return obj.is_active

    @admin.display(description="Compose")
    def compose_link(self, obj):
        if not obj.is_active:
            return format_html('<span style="color:#6b7280;">Disabled</span>')

        return format_html(
            '<a class="button" href="{}">Compose SES Email</a>',
            reverse("admin:mail_ses_compose"),
        )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not SESAccount.all_objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("compose/", self.admin_site.admin_view(self.compose_view), name="mail_ses_compose"),
            path("send/", self.admin_site.admin_view(self.send_action), name="mail_ses_send"),
            path(
                "send-confirmed/",
                self.admin_site.admin_view(self.send_confirmed_action),
                name="mail_ses_send_confirmed",
            ),
            path("preview/", self.admin_site.admin_view(self.preview_action), name="mail_ses_preview"),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        account = SESAccount.get_active()
        extra = {
            "compose_url": reverse("admin:mail_ses_compose") if account else "",
        }
        if extra_context:
            extra.update(extra_context)
        return super().changelist_view(request, extra_context=extra)

    # noinspection PyMethodMayBeStatic
    def _get_active_account(self, request):
        """Return the active SES sender or redirect with an admin error."""
        account = SESAccount.get_active()
        if not account:
            messages.error(
                request,
                "No active SES sender is configured. Re-enable the existing SES Mail Sender first.",
            )
            return None
        return account

    # noinspection PyProtectedMember
    def _build_compose_context(self, request, form, account):
        subscriber_count = Member.objects.filter(email_subscribe=True, is_active=True).count()
        return {
            **self.admin_site.each_context(request),
            "title": "Compose SES Email",
            "opts": self.model._meta,
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

    # noinspection PyMethodMayBeStatic
    def _log_action(self, account, status, request, message_id="", subject="", recipients="", error=""):
        SESEmailLog.objects.create(
            account=account,
            action=SESEmailLog.Action.SEND,
            status=status,
            ses_message_id=message_id,
            subject=subject[:500] if subject else "",
            recipients=recipients,
            error_message=error,
            performed_by=request.user if request.user.is_authenticated else None,
        )
        EmailLog.objects.create(
            account=None,
            action=EmailLog.Action.SEND,
            status=status,
            gmail_message_id=message_id,
            subject=subject[:500] if subject else "",
            recipients=recipients,
            error_message=error,
            performed_by=request.user if request.user.is_authenticated else None,
        )

    def compose_view(self, request):
        account = self._get_active_account(request)
        if not account:
            return redirect(reverse("admin:mail_sesaccount_changelist"))

        form = ComposeForm()
        context = self._build_compose_context(request, form, account)
        return render(request, "admin/mail/compose.html", context)

    def _send_manual(self, request, account, data, attachments):
        """Send a single email to manually-specified recipients."""
        wrapped_html = render_email_layout(data["body"])
        logo_image = get_logo_inline_image()

        try:
            result = SESService(account).send_message(
                to=data["to"],
                subject=data["subject"],
                body_html=wrapped_html,
                cc=data.get("cc", ""),
                bcc=data.get("bcc", ""),
                attachments=attachments or None,
                inline_images=[logo_image],
            )
            self._log_action(
                account,
                SESEmailLog.Status.SUCCESS,
                request,
                message_id=result["id"],
                subject=data["subject"],
                recipients=data["to"],
            )
            account.mark_used()
            messages.success(request, f"SES email sent successfully to {data['to']}")
        except SESServiceError as exc:
            error_msg = str(exc)
            self._log_action(
                account,
                SESEmailLog.Status.FAILED,
                request,
                subject=data["subject"],
                recipients=data["to"],
                error=error_msg,
            )
            account.mark_used(error=error_msg)
            messages.error(request, f"Failed to send SES email: {error_msg}")

    def _send_personalized(self, request, account, data, attachments):
        """Send individual personalized emails and return per-recipient results."""
        recipients = resolve_recipients(data["recipient_source"], data.get("event"))
        if not recipients:
            return []

        include_unsub = data.get("include_unsubscribe_link", False)
        logo_image = get_logo_inline_image()
        ses = SESService(account)
        results = []

        for recipient in recipients:
            body = personalize_body(data["body"], recipient)
            unsub_url = ""
            if include_unsub:
                try:
                    member = Member.objects.get(pk=recipient["member_id"])
                    unsub_url = build_unsubscribe_url(member)
                except Member.DoesNotExist:
                    pass

            wrapped_html = render_email_layout(body, unsubscribe_url=unsub_url)

            try:
                result = ses.send_message(
                    to=recipient["email"],
                    subject=data["subject"],
                    body_html=wrapped_html,
                    attachments=attachments or None,
                    inline_images=[logo_image],
                )
                self._log_action(
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
            except SESServiceError as exc:
                self._log_action(
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

    # noinspection PyProtectedMember
    def send_action(self, request):
        if request.method != "POST":
            return redirect(reverse("admin:mail_ses_compose"))

        account = self._get_active_account(request)
        if not account:
            return redirect(reverse("admin:mail_sesaccount_changelist"))

        form = ComposeForm(request.POST, request.FILES)
        if not form.is_valid():
            context = self._build_compose_context(request, form, account)
            return render(request, "admin/mail/compose.html", context)

        data = form.cleaned_data

        # For bulk sends, show confirmation page first
        if data["recipient_source"] != "manual":
            recipients = resolve_recipients(data["recipient_source"], data.get("event"))
            if not recipients:
                messages.warning(request, "No recipients found for the selected source.")
                return redirect(reverse("admin:mail_ses_compose"))

            source_labels = {"subscribers": "All Subscribers", "event": f"Event: {data.get('event', '')}"}
            context = {
                **self.admin_site.each_context(request),
                "title": "Confirm Send",
                "opts": self.model._meta,
                "recipients": recipients,
                "recipient_count": len(recipients),
                "subject": data["subject"],
                "body": data["body"],
                "recipient_source": data["recipient_source"],
                "event_id": str(data["event"].pk) if data.get("event") else "",
                "include_unsubscribe": data.get("include_unsubscribe_link", False),
                "account_email": account.email,
                "source_label": source_labels.get(data["recipient_source"], data["recipient_source"]),
                "confirm_url": reverse("admin:mail_ses_send_confirmed"),
            }
            return render(request, "admin/mail/ses_confirm.html", context)

        # Manual send — immediate
        attachments = [(uploaded.name, uploaded.read()) for uploaded in request.FILES.getlist("attachments")]
        self._send_manual(request, account, data, attachments)
        return redirect(reverse("admin:mail_sesemaillog_changelist"))

    # noinspection PyProtectedMember
    def send_confirmed_action(self, request):
        """Actually send bulk emails after confirmation."""
        if request.method != "POST":
            return redirect(reverse("admin:mail_ses_compose"))

        account = self._get_active_account(request)
        if not account:
            return redirect(reverse("admin:mail_sesaccount_changelist"))

        # Rebuild data from hidden fields
        from event.models import Event

        recipient_source = request.POST.get("recipient_source", "")
        event_id = request.POST.get("event", "")
        event = None
        if event_id:
            try:
                event = Event.objects.get(pk=event_id)
            except Event.DoesNotExist:
                messages.error(request, "Selected event no longer exists.")
                return redirect(reverse("admin:mail_ses_compose"))

        data = {
            "recipient_source": recipient_source,
            "event": event,
            "subject": request.POST.get("subject", ""),
            "body": request.POST.get("body", ""),
            "include_unsubscribe_link": request.POST.get("include_unsubscribe_link") == "on",
        }

        results = self._send_personalized(request, account, data, attachments=[])
        if not results:
            messages.warning(request, "No recipients found.")
            return redirect(reverse("admin:mail_ses_compose"))

        success_count = sum(1 for r in results if r["status"] == "success")
        fail_count = len(results) - success_count

        context = {
            **self.admin_site.each_context(request),
            "title": "Send Results",
            "opts": self.model._meta,
            "results": results,
            "success_count": success_count,
            "fail_count": fail_count,
            "subject": data["subject"],
        }
        return render(request, "admin/mail/ses_send_status.html", context)

    # noinspection PyMethodMayBeStatic
    def preview_action(self, request):
        """Render the composed email body wrapped in the I2G layout for preview."""
        if request.method != "POST":
            return redirect(reverse("admin:mail_ses_compose"))

        body = request.POST.get("body", "")
        # Replace {name} with a sample name for preview
        body = body.replace("{name}", "Hongzhe")

        include_unsub = request.POST.get("include_unsubscribe_link") == "on"
        unsub_url = "#unsubscribe-preview" if include_unsub else ""

        logo_data_uri = get_logo_data_uri()
        preview_html = render_email_layout(body, logo_src=logo_data_uri, unsubscribe_url=unsub_url)

        # Wrap in a minimal HTML page with centered gray background
        page_html = f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Email Preview</title></head>
<body style="margin:0;padding:40px 20px;background:#f3f4f6;font-family:Arial,sans-serif;">
{preview_html}
</body></html>"""
        return HttpResponse(page_html, content_type="text/html")
