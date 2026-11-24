"""Campaign send confirmation and durable outbox dispatch."""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from unfold.decorators import action

from apps.mail.models import EmailCampaign
from apps.mail.services.campaign.content.retry import (
    RetryRefused,
    assert_retry_campaign_eligible,
    assert_retry_recipients,
)
from apps.mail.services.campaign.content.retry_delivery import delivery_config_for_campaign
from apps.mail.services.campaign.delivery.pacing import delivery_pacing_notice

from . import services as campaign_api


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
        # A plain Admin check, in case the URL is ever mounted without ``admin_view``. State-changing flow
        # (kicks off the background send).
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to send this campaign.")
        obj = EmailCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_emailcampaign_change", args=[object_id])

        if obj.status != "draft":
            messages.warning(request, "This campaign has already been sent.")
            return HttpResponseRedirect(change_url)

        retry_recipients = None
        if obj.retry_source_campaign_id:
            try:
                eligibility = assert_retry_campaign_eligible(obj)
                retry_recipients = campaign_api.get_recipients(obj)
                assert_retry_recipients(obj, retry_recipients, eligibility=eligibility)
            except RetryRefused as exc:
                messages.error(request, f"Retry cannot be sent: {exc}")
                return HttpResponseRedirect(change_url)

        if request.method == "POST":
            from django.conf import settings as django_settings

            if getattr(django_settings, "ADMIN_REQUIRE_CONFIRMATION", True):
                confirmation_text = request.POST.get("confirmation_text", "").strip()
                if confirmation_text != obj.name:
                    messages.error(request, "Confirmation text does not match campaign name. Please try again.")
                    return HttpResponseRedirect(reverse("admin:mail_emailcampaign_send_confirm", args=[object_id]))

            try:
                self._background_send(obj.pk, request.user.pk)
            except RetryRefused as exc:
                messages.error(request, f"Retry was not sent: {exc}")
                return HttpResponseRedirect(change_url)
            except ValueError:
                messages.warning(request, "This campaign has already been sent.")
                return HttpResponseRedirect(change_url)
            except Exception:
                logging.getLogger(__name__).exception("Campaign dispatch failed for %s", obj.pk)
                messages.error(request, "Campaign could not be queued. Check server logs for details.")
                return HttpResponseRedirect(change_url)

            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_send_status", args=[object_id]))

        recipients = retry_recipients if retry_recipients is not None else campaign_api.get_recipients(obj)
        delivery_config = delivery_config_for_campaign(obj)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Confirm Send - {obj.name}",
            "campaign": obj,
            "recipient_count": len(recipients),
            "skipped_count": len(getattr(recipients, "skipped", [])),
            "without_login_link_count": campaign_api.recipients_without_login_link(obj, recipients),
            "delivery_notice": delivery_pacing_notice(delivery_config, len(recipients)),
            "retry_sending_method": delivery_config.get_provider_display() if obj.retry_source_campaign_id else "",
            "retry_from_email": obj.retry_from_email if obj.retry_source_campaign_id else "",
            "preview_url": reverse("admin:mail_emailcampaign_send_preview", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/emailcampaign_send/confirm_send.html", context)

    @staticmethod
    def _background_send(campaign_pk, user_pk):
        """Materialize recipient jobs (or synchronously dispatch during rollout)."""
        from apps.mail.models import EmailCampaign as CampaignModel
        from apps.mail.services.campaign.dispatch import dispatch_email_campaign

        User = get_user_model()
        campaign = CampaignModel.objects.get(pk=campaign_pk)
        user = User.objects.get(pk=user_pk)
        return dispatch_email_campaign(campaign, sent_by=user)
