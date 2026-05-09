"""Campaign admin URL routing mixin."""

from django.urls import path


class CampaignUrlsMixin:
    def get_urls(self):
        custom_urls = [
            path(
                "inline-preview/",
                self.admin_site.admin_view(self.inline_preview_view),
                name="mail_emailcampaign_inline_preview",
            ),
            path(
                "<path:object_id>/import-gmail-html/",
                self.admin_site.admin_view(self.import_gmail_html_view),
                name="mail_emailcampaign_import_gmail_html",
            ),
            path(
                "<path:object_id>/import-gmail-html/confirm/",
                self.admin_site.admin_view(self.import_gmail_html_confirm_view),
                name="mail_emailcampaign_import_gmail_html_confirm",
            ),
            path(
                "<path:object_id>/preview-recipients/",
                self.admin_site.admin_view(self.preview_recipients_view),
                name="mail_emailcampaign_preview_recipients",
            ),
            path(
                "<path:object_id>/send-campaign/",
                self.admin_site.admin_view(self.send_campaign_preview_view),
                name="mail_emailcampaign_send_preview",
            ),
            path(
                "<path:object_id>/send-campaign/confirm/",
                self.admin_site.admin_view(self.send_campaign_confirm_view),
                name="mail_emailcampaign_send_confirm",
            ),
            path(
                "<path:object_id>/send-campaign/status/",
                self.admin_site.admin_view(self.send_campaign_status_view),
                name="mail_emailcampaign_send_status",
            ),
            path(
                "<path:object_id>/send-campaign/status.json",
                self.admin_site.admin_view(self.send_campaign_status_json),
                name="mail_emailcampaign_send_status_json",
            ),
        ]
        return custom_urls + super().get_urls()
