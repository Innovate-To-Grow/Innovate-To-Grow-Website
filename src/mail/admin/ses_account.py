"""
Admin configuration for the SES sender with a dedicated compose flow.
"""

import logging

from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from core.admin.base import BaseModelAdmin
from mail.forms import ComposeForm
from mail.models import SESAccount
from mail.services.ses import SESService, SESServiceError

from .ses.helpers import (
    build_compose_context,
    compose_view,
    get_active_account,
    preview_action,
    send_manual,
    send_personalized,
)

logger = logging.getLogger(__name__)


@admin.register(SESAccount)
class SESAccountAdmin(BaseModelAdmin):
    """Admin for the dedicated SES sender used by the new I2G system."""

    change_list_template = "admin/mail/sesaccount/change_list.html"
    list_display = ("email", "display_name", "is_active_badge", "compose_link", "last_used_at", "updated_at")
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
        return format_html('<a class="button" href="{}">Compose SES Email</a>', reverse("admin:mail_ses_compose"))

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not SESAccount.all_objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
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
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        account = SESAccount.get_active()
        extra = {"compose_url": reverse("admin:mail_ses_compose") if account else ""}
        return super().changelist_view(request, extra_context={**(extra_context or {}), **extra})

    def compose_view(self, request):
        return compose_view(self, request)

    def send_action(self, request):
        if request.method != "POST":
            return redirect(reverse("admin:mail_ses_compose"))
        account = get_active_account(request)
        if not account:
            return redirect(reverse("admin:mail_sesaccount_changelist"))
        form = ComposeForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, "admin/mail/compose.html", build_compose_context(self, request, form, account))

        data = form.cleaned_data
        if data["recipient_source"] != "manual":
            from mail.services.recipients import resolve_recipients

            recipients = resolve_recipients(data["recipient_source"], data.get("event"))
            if not recipients:
                from django.contrib import messages

                messages.warning(request, "No recipients found for the selected source.")
                return redirect(reverse("admin:mail_ses_compose"))
            source_labels = {"subscribers": "All Subscribers", "event": f"Event: {data.get('event', '')}"}
            return render(
                request,
                "admin/mail/ses_confirm.html",
                {
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
                },
            )

        attachments = [(uploaded.name, uploaded.read()) for uploaded in request.FILES.getlist("attachments")]
        send_manual(request, account, data, attachments, SESService, SESServiceError)
        return redirect(reverse("admin:mail_sesemaillog_changelist"))

    def send_confirmed_action(self, request):
        if request.method != "POST":
            return redirect(reverse("admin:mail_ses_compose"))
        account = get_active_account(request)
        if not account:
            return redirect(reverse("admin:mail_sesaccount_changelist"))

        from django.contrib import messages

        from event.models import Event

        event = None
        event_id = request.POST.get("event", "")
        if event_id:
            try:
                event = Event.objects.get(pk=event_id)
            except Event.DoesNotExist:
                messages.error(request, "Selected event no longer exists.")
                return redirect(reverse("admin:mail_ses_compose"))

        results = send_personalized(
            request,
            account,
            {
                "recipient_source": request.POST.get("recipient_source", ""),
                "event": event,
                "subject": request.POST.get("subject", ""),
                "body": request.POST.get("body", ""),
                "include_unsubscribe_link": request.POST.get("include_unsubscribe_link") == "on",
            },
            SESService,
            SESServiceError,
            logger,
        )
        if not results:
            messages.warning(request, "No recipients found.")
            return redirect(reverse("admin:mail_ses_compose"))

        success_count = sum(1 for result in results if result["status"] == "success")
        return render(
            request,
            "admin/mail/ses_send_status.html",
            {
                **self.admin_site.each_context(request),
                "title": "Send Results",
                "opts": self.model._meta,
                "results": results,
                "success_count": success_count,
                "fail_count": len(results) - success_count,
                "subject": request.POST.get("subject", ""),
            },
        )

    def preview_action(self, request):
        return preview_action(request)
