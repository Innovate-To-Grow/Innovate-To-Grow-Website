"""A Broadcast SMS campaign's own status and counts while the in-process sender sends it."""


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
    from apps.mail.services.campaign.dispatch import aggregate_sms_campaign

    # Derive progress from the persisted logs (sent, failed, paused, still pending) instead of counting in memory.
    aggregate_sms_campaign(campaign.pk)
    campaign.refresh_from_db(
        fields=["status", "total_recipients", "sent_count", "failed_count", "sent_at", "error_message"]
    )


def _fail_campaign_for_missing_sms_config(campaign):
    campaign.status = "failed"
    campaign.error_message = "SMS delivery is not configured. Check AWS Credentials in admin."
    campaign.save(update_fields=["status", "error_message"])
    raise RuntimeError("SMS delivery is not configured. Cannot send campaign.")
