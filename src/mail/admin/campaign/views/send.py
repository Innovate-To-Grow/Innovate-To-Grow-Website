"""Campaign send confirmation and background execution."""

import json
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from unfold.decorators import action

import mail.admin.campaign as campaign_api
from mail.models import EmailCampaign


class CampaignSendMixin:
    @action(description="Send Campaign", url_path="send-campaign", icon="send")
    def send_campaign_action(self, request, object_id):
        obj = EmailCampaign.objects.get(pk=object_id)
        if obj.status != "draft":
            messages.warning(request, "This campaign has already been sent.")
            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_change", args=[object_id]))
        return HttpResponseRedirect(reverse("admin:mail_emailcampaign_send_preview", args=[object_id]))

    def send_campaign_confirm_view(self, request, object_id):
        """Final confirmation before sending."""
        obj = EmailCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_emailcampaign_change", args=[object_id])

        if obj.status != "draft":
            messages.warning(request, "This campaign has already been sent.")
            return HttpResponseRedirect(change_url)

        if request.method == "POST":
            from django.conf import settings as django_settings

            if getattr(django_settings, "ADMIN_REQUIRE_CONFIRMATION", True):
                confirmation_text = request.POST.get("confirmation_text", "").strip()
                if confirmation_text != obj.name:
                    messages.error(request, "Confirmation text does not match campaign name. Please try again.")
                    return HttpResponseRedirect(reverse("admin:mail_emailcampaign_send_confirm", args=[object_id]))

            recipients = campaign_api.get_recipients(obj)
            recipient_count = len(recipients)

            thread = campaign_api.threading.Thread(
                target=self._background_send,
                args=(obj.pk, request.user.pk),
                daemon=False,
            )
            thread.start()

            from core.admin.notifications import notify_staff_of_action

            notify_staff_of_action(
                actor=request.user,
                action=f"Sent Campaign: {obj.name}",
                summary=[
                    {"label": "Campaign", "value": obj.name},
                    {"label": "Subject", "value": obj.subject},
                    {"label": "Audience", "value": obj.get_audience_type_display()},
                    {"label": "Recipients", "value": str(recipient_count)},
                ],
                admin_url=request.build_absolute_uri(change_url),
            )

            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_send_status", args=[object_id]))

        recipients = campaign_api.get_recipients(obj)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Confirm Send - {obj.name}",
            "campaign": obj,
            "recipient_count": len(recipients),
            "campaign_name_json": json.dumps(obj.name),
            "preview_url": reverse("admin:mail_emailcampaign_send_preview", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/confirm_send.html", context)

    @staticmethod
    def _background_send(campaign_pk, user_pk):
        """Run send_campaign in a background thread."""
        import django

        django.db.connections.close_all()
        from mail.models import EmailCampaign as CampaignModel
        from mail.services.send_campaign import send_campaign

        User = get_user_model()
        campaign = CampaignModel.objects.get(pk=campaign_pk)
        user = User.objects.get(pk=user_pk)
        try:
            send_campaign(campaign, sent_by=user)
        except Exception:
            logging.getLogger(__name__).exception("Background send failed for campaign %s", campaign_pk)
            campaign.refresh_from_db()
            if campaign.status in ("draft", "sending"):
                campaign.status = "failed"
            campaign.error_message = "Campaign send failed. Check server logs for details."
            campaign.save(update_fields=["status", "error_message"])
        finally:
            django.db.connections.close_all()
