"""The SMS campaign admin's preview, send-confirmation and live-status views."""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.mail.admin.campaign.views.status import _short_error
from apps.mail.models import SmsCampaign, SmsRecipientLog
from apps.mail.services.campaign.personalize import personalize
from apps.mail.services.sms.audience import get_sms_recipients


class SmsCampaignSendViewsMixin:
    """Mixed into ``SmsCampaignAdmin``, whose ``get_urls`` routes these views."""

    def preview_recipients_view(self, request, object_id):
        # ``admin_view`` only enforces is_staff, so this custom URL must re-check
        # per-app access itself — Django never runs the per-app model permissions
        # for a standalone admin view.
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to view SMS campaign recipients.")
        obj = SmsCampaign.objects.get(pk=object_id)
        recipients = get_sms_recipients(obj)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Preview SMS Recipients - {obj.name}",
            "campaign": obj,
            "recipients": recipients,
            "back_url": reverse("admin:mail_smscampaign_change", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/smscampaign/preview_recipients.html", context)

    def send_sms_preview_view(self, request, object_id):
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to preview this SMS campaign.")
        obj = SmsCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_smscampaign_change", args=[object_id])
        recipients = get_sms_recipients(obj)
        preview = personalize(
            obj.message,
            {
                "first_name": "Hongzhe",
                "last_name": "Xie",
                "full_name": "Hongzhe Xie",
            },
        )
        context = {
            **self.admin_site.each_context(request),
            "title": f"Preview SMS - {obj.name}",
            "campaign": obj,
            "recipient_count": len(recipients),
            "preview_message": preview,
            "confirm_url": reverse("admin:mail_smscampaign_send_confirm", args=[object_id])
            if obj.status == "draft"
            else None,
            "cancel_url": change_url,
        }
        return TemplateResponse(request, "admin/mail/smscampaign/send_preview.html", context)

    def send_sms_confirm_view(self, request, object_id):
        # State-changing flow (triggers the background SMS send) — require change access.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to send this SMS campaign.")
        obj = SmsCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_smscampaign_change", args=[object_id])
        if obj.status != "draft":
            messages.warning(request, "This SMS campaign has already been sent.")
            return HttpResponseRedirect(change_url)

        if request.method == "POST":
            from django.conf import settings as django_settings

            if getattr(django_settings, "ADMIN_REQUIRE_CONFIRMATION", True):
                confirmation_text = request.POST.get("confirmation_text", "").strip()
                if confirmation_text != obj.name:
                    messages.error(request, "Confirmation text does not match campaign name. Please try again.")
                    return HttpResponseRedirect(reverse("admin:mail_smscampaign_send_confirm", args=[object_id]))

            try:
                self._background_send(obj.pk, request.user.pk)
            except ValueError:
                messages.warning(request, "This SMS campaign has already been sent.")
                return HttpResponseRedirect(change_url)
            except Exception:
                logging.getLogger(__name__).exception("SMS campaign dispatch failed for %s", obj.pk)
                messages.error(request, "SMS campaign could not be queued. Check server logs for details.")
                return HttpResponseRedirect(change_url)

            return HttpResponseRedirect(reverse("admin:mail_smscampaign_send_status", args=[object_id]))

        recipients = get_sms_recipients(obj)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Confirm SMS Send - {obj.name}",
            "campaign": obj,
            "recipient_count": len(recipients),
            "preview_url": reverse("admin:mail_smscampaign_send_preview", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/smscampaign/confirm_send.html", context)

    def send_sms_status_view(self, request, object_id):
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to view this SMS campaign's status.")
        obj = SmsCampaign.objects.get(pk=object_id)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Sending SMS - {obj.name}",
            "campaign": obj,
            "status_json_url": reverse("admin:mail_smscampaign_send_status_json", args=[object_id]),
            "back_url": reverse("admin:mail_smscampaign_change", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/smscampaign/send_status.html", context)

    def send_sms_status_json(self, request, object_id):
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to view this SMS campaign's status.")
        obj = SmsCampaign.objects.get(pk=object_id)
        recent_logs = [
            {
                "phone": log.phone_number,
                "name": log.recipient_name,
                "status": log.status,
                "error": _short_error(log.error_message),
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
            }
            for log in SmsRecipientLog.objects.filter(campaign=obj)
            .exclude(status="pending")
            .order_by("-updated_at")[:20]
        ]
        failed_logs = [
            {
                "phone": log.phone_number,
                "name": log.recipient_name,
                "error": _short_error(log.error_message),
            }
            for log in SmsRecipientLog.objects.filter(
                campaign=obj,
                status__in=["failed", "uncertain"],
            ).order_by("-updated_at")
        ]
        first_sent_at = (
            SmsRecipientLog.objects.filter(campaign=obj, sent_at__isnull=False)
            .order_by("sent_at")
            .values_list("sent_at", flat=True)
            .first()
        )
        return JsonResponse(
            {
                "status": obj.status,
                "total": obj.total_recipients,
                "sent": obj.sent_count,
                "failed": obj.failed_count,
                "error_message": _short_error(obj.error_message),
                "started_at": first_sent_at.isoformat() if first_sent_at else None,
                "recent_logs": recent_logs,
                "failed_logs": failed_logs,
            }
        )

    @staticmethod
    def _background_send(campaign_pk, user_pk):
        from apps.mail.models import SmsCampaign as CampaignModel
        from apps.mail.services.campaign.dispatch import dispatch_sms_campaign

        User = get_user_model()
        campaign = CampaignModel.objects.get(pk=campaign_pk)
        user = User.objects.get(pk=user_pk)
        return dispatch_sms_campaign(campaign, sent_by=user)
