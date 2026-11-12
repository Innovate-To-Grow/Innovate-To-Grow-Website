"""A Delivery Dashboard payload (``apps.mail.services.campaign.dashboard.get_delivery_dashboard_data``) for the Amazon
SES tab's tests: made-up AWS figures and example.com addresses only, no AWS call."""

from copy import deepcopy

PATCH_DASHBOARD = "apps.mail.admin.email_monitoring.ses.get_delivery_dashboard_data"

_PAYLOAD = {
    "window_days": 183,
    "generated_at": "2026-06-08T12:00:00+00:00",
    "summary": {
        "attempts": 120,
        "success": 116,
        "problems": 4,
        "failure_rate": 3.3,
        "campaign_attempts": 0,
        "campaign_errors": 0,
        "ticket_sent": 0,
        "ticket_errors": 0,
        "pending": 0,
        "bounces": 3,
        "complaints": 1,
        "rejected": 0,
        "failed": 0,
        "delayed": 2,
    },
    "aws": {
        "configured": True,
        "provider": "ses",
        "provider_label": "AWS SES",
        "email_config": "Production Mail",
        "aws_config": "Primary AWS",
        "region": "us-west-2",
        "source_address": "I2G Admin <admin@example.com>",
        "send_rate": "Now: 12 recipients/sec · Smart",
        "iam_key": "...1234",
        "metrics_available": True,
        "metrics_reason": "",
        "metrics_source": "CloudWatch account SES metrics",
        "recipient_details_available": True,
        "recipient_details_reason": "",
        "recipient_details_error_code": "",
        "recipient_details_error_message": "",
        "recipient_details_required_actions": [],
    },
    "metrics": {
        "available": True,
        "reason": "",
        "source": "CloudWatch account SES metrics",
        "namespace": "AWS/SES",
        "dimension_count": 1,
    },
    "recipient_details": {
        "available": True,
        "reason": "",
        "source": "AWS SES account suppression list",
        "count": 2,
        "error_code": "",
        "error_message": "",
        "required_actions": [],
        "returned_count": 2,
        "total_count": 2,
        "truncated": False,
        "limit": None,
        "reason_counts": {"BOUNCE": 1, "COMPLAINT": 1},
        "latest_seen": "Jun 08, 12:00",
        "window_days": 183,
    },
    "daily": [
        {"date": "2026-06-06", "attempts": 0, "problems": 0},
        {"date": "2026-06-07", "attempts": 20, "problems": 0},
        {"date": "2026-06-08", "attempts": 100, "problems": 4},
    ],
    "status_breakdown": [
        {"status": "bounced", "label": "Bounced", "count": 3},
        {"status": "complained", "label": "Complained", "count": 1},
        {"status": "delayed", "label": "Delivery delays", "count": 2},
        {"status": "delivered", "label": "Delivered", "count": 116},
        {"status": "sent", "label": "Sent", "count": 120},
    ],
    "problem_recipients": [
        {
            "email": "bounce@example.com",
            "name": "",
            "source": "AWS SES Suppression List",
            "context": "Account-level suppression",
            "status": "bounced",
            "label": "Bounced",
            "reason": "BOUNCE",
            "last_seen": "Jun 08, 12:00",
            "count": 1,
        },
        {
            "email": "complaint@example.org",
            "name": "",
            "source": "AWS SES Suppression List",
            "context": "Account-level suppression",
            "status": "complained",
            "label": "Complained",
            "reason": "COMPLAINT",
            "last_seen": "Jun 07, 12:00",
            "count": 1,
        },
    ],
}


def ses_payload(*, window_days: int = 183, aws: dict | None = None, details: dict | None = None, **changes) -> dict:
    """A fresh copy of the payload for ``window_days``; ``aws`` and ``details`` update those parts, other keyword
    arguments replace top-level keys."""
    payload = deepcopy(_PAYLOAD)
    payload["window_days"] = window_days
    payload["recipient_details"]["window_days"] = window_days
    payload["aws"].update(aws or {})
    payload["recipient_details"].update(details or {})
    payload.update(changes)
    return payload
