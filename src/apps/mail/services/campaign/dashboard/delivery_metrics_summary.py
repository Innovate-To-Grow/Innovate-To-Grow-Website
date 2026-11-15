from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

METRICS = (
    ("Send", "attempts", "Sent"),
    ("Delivery", "success", "Delivered"),
    ("Bounce", "bounces", "Bounced"),
    ("Complaint", "complaints", "Complained"),
    ("Reject", "rejected", "Rejected"),
    ("RenderingFailure", "failed", "Rendering failures"),
    ("DeliveryDelay", "delayed", "Delivery delays"),
)


def _zero_summary() -> dict:
    return {
        "attempts": 0,
        "success": 0,
        "problems": 0,
        "failure_rate": 0,
        "campaign_attempts": 0,
        "campaign_errors": 0,
        "ticket_sent": 0,
        "ticket_errors": 0,
        "pending": 0,
        "bounces": 0,
        "complaints": 0,
        "rejected": 0,
        "failed": 0,
        "delayed": 0,
    }


def _empty_daily_map(days: int, now):
    today = timezone.localdate(now)
    return {
        (today - timedelta(days=offset)).isoformat(): {key: 0 for _metric_name, key, _label in METRICS}
        for offset in range(days - 1, -1, -1)
    }


def _status_breakdown(summary: dict) -> list[dict]:
    mapping = (
        ("bounces", "bounced", "Bounced"),
        ("complaints", "complained", "Complained"),
        ("rejected", "rejected", "Rejected"),
        ("failed", "failed", "Rendering failures"),
        ("delayed", "delayed", "Delivery delays"),
        ("success", "delivered", "Delivered"),
        ("attempts", "sent", "Sent"),
    )
    return [
        {"status": status, "label": label, "count": summary[key]} for key, status, label in mapping if summary.get(key)
    ]
