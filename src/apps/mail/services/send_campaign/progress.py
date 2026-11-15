"""A campaign's own status and counts while the in-process runner sends it."""

from apps.mail.models import RecipientLog


def _mark_campaign_sending(campaign, sent_by, recipient_count):
    campaign.status = "sending"
    campaign.sent_by = sent_by
    campaign.total_recipients = recipient_count
    campaign.sent_count = 0
    campaign.failed_count = 0
    campaign.error_message = ""
    campaign.save(
        update_fields=[
            "status",
            "sent_by",
            "total_recipients",
            "sent_count",
            "failed_count",
            "error_message",
        ]
    )


def _finalize_campaign(campaign):
    _refresh_campaign_progress(campaign)
    return {
        "total": campaign.total_recipients,
        "sent": campaign.sent_count,
        "failed": campaign.failed_count,
    }


def _refresh_campaign_progress(campaign):
    from apps.mail.services.campaign.dispatch import aggregate_email_campaign

    # SES callbacks update the same rows while this loop is running. Always
    # derive progress from persisted logs instead of overwriting their counts.
    aggregate_email_campaign(campaign.pk)
    campaign.refresh_from_db(
        fields=["status", "total_recipients", "sent_count", "failed_count", "sent_at", "error_message"]
    )


def _fail_campaign_for_missing_delivery_config(campaign, recipients):
    error_message = "Email delivery is not configured. Check Notification Delivery in admin."
    for recipient in recipients:
        RecipientLog.objects.update_or_create(
            campaign=campaign,
            email_address=recipient["email"],
            defaults={
                "member_id": recipient["member_id"],
                "recipient_name": recipient["full_name"],
                "status": "failed",
                "provider": "",
                "error_message": error_message,
            },
        )
    campaign.status = "failed"
    campaign.failed_count = len(recipients)
    campaign.error_message = error_message
    campaign.save(update_fields=["status", "failed_count", "error_message"])
    raise RuntimeError("Email delivery is not configured. Cannot send campaign.")
