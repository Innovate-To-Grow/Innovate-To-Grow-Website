"""Campaign send confirmation and durable outbox dispatch."""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from unfold.decorators import action

import apps.mail.admin.campaign as campaign_api
from apps.mail.models import EmailCampaign


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
        # ``admin_view`` only enforces is_staff, so this custom URL must re-check
        # per-app access itself. State-changing flow (kicks off the background
        # send) — require change access.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to send this campaign.")
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

            try:
                self._background_send(obj.pk, request.user.pk)
            except ValueError:
                messages.warning(request, "This campaign has already been sent.")
                return HttpResponseRedirect(change_url)
            except Exception:
                logging.getLogger(__name__).exception("Campaign dispatch failed for %s", obj.pk)
                messages.error(request, "Campaign could not be queued. Check server logs for details.")
                return HttpResponseRedirect(change_url)

            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_send_status", args=[object_id]))

        recipients = campaign_api.get_recipients(obj)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Confirm Send - {obj.name}",
            "campaign": obj,
            "recipient_count": len(recipients),
            "preview_url": reverse("admin:mail_emailcampaign_send_preview", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/confirm_send.html", context)

    @staticmethod
    def _background_send(campaign_pk, user_pk):
        """Materialize recipient jobs (or synchronously dispatch during rollout)."""
        from apps.mail.models import EmailCampaign as CampaignModel
        from apps.mail.services.campaign.dispatch import dispatch_email_campaign

        User = get_user_model()
        campaign = CampaignModel.objects.get(pk=campaign_pk)
        user = User.objects.get(pk=user_pk)
        return dispatch_email_campaign(campaign, sent_by=user)
