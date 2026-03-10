"""
Admin configuration for the SES sender with a dedicated compose flow.
"""

from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from core.admin.base import BaseModelAdmin
from mail.forms import ComposeForm
from mail.models import EmailLog, SESAccount, SESEmailLog
from mail.services.ses import SESService, SESServiceError


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
        context = {
            **self.admin_site.each_context(request),
            "title": "Compose SES Email",
            "opts": self.model._meta,
            "form": form,
            "account_email": account.email,
            "send_url": reverse("admin:mail_ses_send"),
            "cancel_url": reverse("admin:mail_sesaccount_changelist"),
            "parent_label": "SES Mail Senders",
            "parent_url": reverse("admin:mail_sesaccount_changelist"),
        }
        return render(request, "admin/mail/compose.html", context)

    def send_action(self, request):
        if request.method != "POST":
            return redirect(reverse("admin:mail_ses_compose"))

        account = self._get_active_account(request)
        if not account:
            return redirect(reverse("admin:mail_sesaccount_changelist"))

        form = ComposeForm(request.POST, request.FILES)
        if not form.is_valid():
            context = {
                **self.admin_site.each_context(request),
                "title": "Compose SES Email",
                "opts": self.model._meta,
                "form": form,
                "account_email": account.email,
                "send_url": reverse("admin:mail_ses_send"),
                "cancel_url": reverse("admin:mail_sesaccount_changelist"),
                "parent_label": "SES Mail Senders",
                "parent_url": reverse("admin:mail_sesaccount_changelist"),
            }
            return render(request, "admin/mail/compose.html", context)

        data = form.cleaned_data
        attachments = [(uploaded.name, uploaded.read()) for uploaded in request.FILES.getlist("attachments")]

        try:
            result = SESService(account).send_message(
                to=data["to"],
                subject=data["subject"],
                body_html=data["body"],
                cc=data.get("cc", ""),
                bcc=data.get("bcc", ""),
                attachments=attachments or None,
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

        return redirect(reverse("admin:mail_sesemaillog_changelist"))
