"""Campaign send status views."""

import logging
import uuid

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse
from unfold.decorators import action

from apps.core.services.delivery_rates import Family, active_target, channel_status
from apps.mail.models import EmailCampaign, RecipientLog

logger = logging.getLogger(__name__)

# Recipients still to be sent: not started, being sent, or waiting for the slot the delivery limits give them.
QUEUED_STATUSES = ("pending", "processing", "retry")


class CampaignStatusMixin:
    @action(description="Delivery monitoring", url_path="delivery-monitoring", icon="monitoring")
    def delivery_monitoring_action(self, request, object_id):
        """Mail → Delivery Operations → Email Monitoring for this campaign (shown once it has been sent)."""
        try:
            campaign_id = uuid.UUID(str(object_id))
        except ValueError:
            raise Http404("Campaign not found.") from None
        return HttpResponseRedirect(reverse("admin:mail_email_monitoring_campaign", args=[campaign_id]))

    def send_campaign_status_view(self, request, object_id):
        """Live send progress page."""
        # ``admin_view`` only enforces is_staff, so this custom URL must re-check
        # per-app access itself.
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to view this campaign's status.")
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
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to view this campaign's status.")
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
            for log in RecipientLog.objects.filter(
                campaign=obj,
                status__in=["failed", "uncertain"],
            ).order_by("-updated_at")
        ]
        first_sent_at = (
            RecipientLog.objects.filter(campaign=obj, sent_at__isnull=False)
            .order_by("sent_at")
            .values_list("sent_at", flat=True)
            .first()
        )
        counts = _status_counts(obj)
        payload = {
            "status": obj.status,
            "total": obj.total_recipients,
            "sent": obj.sent_count,
            "failed": obj.failed_count,
            # Still to go: queued for their turn (``retrying``: held back by the delivery limits, sent again at
            # their slot) or paused by a longer hold, which "Resume paused recipients" sends later.
            "queued": sum(counts.get(status, 0) for status in QUEUED_STATUSES),
            "retrying": counts.get("retry", 0),
            "paused": counts.get("paused", 0),
            "delivery": _delivery_status(),
            "error_message": _short_error(obj.error_message),
            "started_at": first_sent_at.isoformat() if first_sent_at else None,
            "recent_logs": recent_logs,
            "failed_logs": failed_logs,
        }
        cache.set(status_cache_key, payload, 2)
        return JsonResponse(payload)


def _status_counts(campaign) -> dict:
    rows = RecipientLog.objects.filter(campaign=campaign).values("status").annotate(count=Count("id"))
    return {row["status"]: row["count"] for row in rows}


def _delivery_status() -> dict | None:
    """The active email channel as the delivery limiter sees it now: its headline ("Now: 19.2 messages/min …",
    "Paused until …", "Stopped: …"), whether a pause or stop holds it, and its budget lines. None when email is not
    configured or the limiter cannot be read (the campaign's own progress still shows)."""
    try:
        target = active_target(Family.EMAIL)
        if target is None:
            return None
        status = channel_status(target.channel)
        identity = next((item for item in status.identities if item.identity == target.identity), status.identities[0])
    except Exception:  # noqa: BLE001 - a broken limiter read must not take the status page down with it.
        logger.warning("The delivery status could not be read for the campaign status page", exc_info=True)
        return None
    return {
        "lines": list(identity.lines),
        "held": bool(identity.cooldown_until or identity.breaker_open),
    }


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
