from typing import Any

from django.db.models import Count

from system_intelligence.services.actions.exceptions import ActionRequestError

from ..query_helpers import object_payload, queryset_payload, require_one
from ..runtime import run_action_service_async


async def get_campaign_recipient_logs(
    campaign_id: str | None = None,
    campaign_name: str | None = None,
    status: str | None = None,
    email: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Search recipient logs for one campaign by delivery status or email."""
    return await run_action_service_async(
        _get_campaign_recipient_logs, campaign_id, campaign_name, status, email, limit
    )


async def get_failed_recipient_report(
    campaign_id: str | None = None, campaign_name: str | None = None
) -> dict[str, Any]:
    """Summarize failed, bounced, complained, and rejected recipients for one campaign."""
    return await run_action_service_async(_get_failed_recipient_report, campaign_id, campaign_name)


def _find_campaign(campaign_id: str | None = None, campaign_name: str | None = None):
    from mail.models import EmailCampaign

    qs = EmailCampaign.objects.all()
    if campaign_id:
        return require_one(qs.filter(pk=campaign_id), "Email campaign")
    if campaign_name:
        return require_one(qs.filter(name__icontains=campaign_name).order_by("-created_at"), "Email campaign")
    raise ActionRequestError("Provide campaign_id or campaign_name.")


def _campaign_payload(campaign) -> dict[str, Any]:
    return object_payload(
        campaign,
        [
            "id",
            "name",
            "subject",
            "audience_type",
            "status",
            "total_recipients",
            "sent_count",
            "failed_count",
            "sent_at",
            "created_at",
            "updated_at",
        ],
    )


def _get_campaign_recipient_logs(campaign_id=None, campaign_name=None, status=None, email=None, limit=None):
    campaign = _find_campaign(campaign_id, campaign_name)
    logs = campaign.recipient_logs.all()
    if status:
        logs = logs.filter(status=status)
    if email:
        logs = logs.filter(email_address__icontains=email)
    return {
        "campaign": _campaign_payload(campaign),
        "status_breakdown": list(logs.values("status").annotate(count=Count("id")).order_by("status")),
        "recipient_logs": queryset_payload(
            logs.order_by("-updated_at"),
            [
                "id",
                "email_address",
                "recipient_name",
                "status",
                "provider",
                "error_message",
                "sent_at",
                "delivered_at",
                "bounced_at",
                "complained_at",
                "last_event_type",
                "last_event_at",
                "updated_at",
            ],
            limit=limit,
        ),
    }


def _get_failed_recipient_report(campaign_id=None, campaign_name=None):
    campaign = _find_campaign(campaign_id, campaign_name)
    failed_statuses = ["failed", "bounced", "complained", "rejected"]
    logs = campaign.recipient_logs.filter(status__in=failed_statuses)
    return {
        "campaign": _campaign_payload(campaign),
        "failure_count": logs.count(),
        "by_status": list(logs.values("status").annotate(count=Count("id")).order_by("status")),
        "by_bounce_type": list(logs.values("bounce_type").annotate(count=Count("id")).order_by("bounce_type")),
        "failed_recipients": queryset_payload(
            logs.order_by("-updated_at"),
            ["id", "email_address", "recipient_name", "status", "error_message", "bounce_type", "bounce_subtype"],
            limit=50,
        )["rows"],
    }
