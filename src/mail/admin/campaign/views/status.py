"""Campaign send status views."""

from django.core.cache import cache
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse

from mail.models import EmailCampaign, RecipientLog


class CampaignStatusMixin:
    def send_campaign_status_view(self, request, object_id):
        """Live send progress page."""
        obj = EmailCampaign.objects.get(pk=object_id)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Sending - {obj.name}",
            "campaign": obj,
            "status_json_url": reverse("admin:mail_emailcampaign_send_status_json", args=[object_id]),
            "back_url": reverse("admin:mail_emailcampaign_change", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/send_status.html", context)

    def send_campaign_status_json(self, request, object_id):
        """JSON endpoint for polling send progress."""
        status_cache_key = f"mail:campaign_status:{object_id}"
        cached = cache.get(status_cache_key)
        if cached is not None:
            return JsonResponse(cached)

        obj = EmailCampaign.objects.get(pk=object_id)
        recent_logs = [
            {
                "email": log.email_address,
                "name": log.recipient_name,
                "status": log.status,
                "error": _short_error(log.error_message),
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
            }
            for log in RecipientLog.objects.filter(campaign=obj).exclude(status="pending").order_by("-updated_at")[:20]
        ]
        failed_logs = [
            {
                "email": log.email_address,
                "name": log.recipient_name,
                "error": _short_error(log.error_message),
            }
            for log in RecipientLog.objects.filter(campaign=obj, status="failed").order_by("-updated_at")
        ]
        first_sent_at = (
            RecipientLog.objects.filter(campaign=obj, sent_at__isnull=False)
            .order_by("sent_at")
            .values_list("sent_at", flat=True)
            .first()
        )
        payload = {
            "status": obj.status,
            "total": obj.total_recipients,
            "sent": obj.sent_count,
            "failed": obj.failed_count,
            "error_message": _short_error(obj.error_message),
            "started_at": first_sent_at.isoformat() if first_sent_at else None,
            "recent_logs": recent_logs,
            "failed_logs": failed_logs,
        }
        cache.set(status_cache_key, payload, 2)
        return JsonResponse(payload)


def _short_error(msg: object) -> str:
    """Trim error strings before they flow into the JSON response."""
    if not msg:
        return ""
    text = str(msg)
    if "Traceback (most recent call last)" in text or '\n  File "' in text:
        return "Send failed (see server logs for details)."
    first_line = text.splitlines()[0] if text else ""
    cleaned = "".join(ch for ch in first_line if ch.isprintable())
    return cleaned[:200]
