"""Broadcast SMS campaign admin."""

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from unfold.decorators import action

from apps.core.services.background_jobs import jobs_enabled
from apps.mail.models import SmsCampaign


class SmsCampaignActionsMixin:
    """SmsCampaignAdmin's admin actions and its own URLs (recipient preview, send flow)."""

    @admin.action(description="Resume paused recipients (held back by delivery limits)", permissions=["change"])
    def resume_paused_recipients_action(self, request, queryset):
        from apps.mail.services.campaign.dispatch import resume_paused_sms_recipients
        from apps.mail.services.sms.policy.errors import SmsSendRefused

        try:
            resumed = sum(resume_paused_sms_recipients(campaign) for campaign in queryset)
        except SmsSendRefused as exc:
            self.message_user(request, str(exc), messages.WARNING)
            return
        if not resumed:
            self.message_user(request, "No paused recipients to resume (or the campaign is still sending).")
            return
        how = "queued for the background worker" if jobs_enabled() else "being sent by the web server"
        self.message_user(request, f"Resumed {resumed} paused recipient(s): {how}.", messages.SUCCESS)

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/preview-recipients/",
                self.admin_site.admin_view(self.preview_recipients_view),
                name="mail_smscampaign_preview_recipients",
            ),
            path(
                "<path:object_id>/send-sms/",
                self.admin_site.admin_view(self.send_sms_preview_view),
                name="mail_smscampaign_send_preview",
            ),
            path(
                "<path:object_id>/send-sms/confirm/",
                self.admin_site.admin_view(self.send_sms_confirm_view),
                name="mail_smscampaign_send_confirm",
            ),
            path(
                "<path:object_id>/send-sms/status/",
                self.admin_site.admin_view(self.send_sms_status_view),
                name="mail_smscampaign_send_status",
            ),
            path(
                "<path:object_id>/send-sms/status.json",
                self.admin_site.admin_view(self.send_sms_status_json),
                name="mail_smscampaign_send_status_json",
            ),
        ]
        return custom_urls + super().get_urls()

    @action(description="Preview SMS", url_path="preview-sms", icon="visibility")
    def preview_sms_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_smscampaign_send_preview", args=[object_id]))

    @action(description="Preview Recipients", url_path="preview-recipients", icon="group")
    def preview_recipients_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_smscampaign_preview_recipients", args=[object_id]))

    @action(description="Send SMS Campaign", url_path="send-sms", icon="send")
    def send_sms_campaign_action(self, request, object_id):
        obj = SmsCampaign.objects.get(pk=object_id)
        if obj.status != "draft":
            messages.warning(request, "This SMS campaign has already been sent.")
            return HttpResponseRedirect(reverse("admin:mail_smscampaign_change", args=[object_id]))
        return HttpResponseRedirect(reverse("admin:mail_smscampaign_send_preview", args=[object_id]))
