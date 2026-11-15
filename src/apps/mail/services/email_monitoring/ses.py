"""Email Monitoring → Amazon SES: the figures of the former Delivery Dashboard, arranged for the tab.

The figures come from ``apps.mail.services.campaign.dashboard`` unchanged: daily sums of the AWS CloudWatch ``AWS/SES``
metrics for the AWS account (or its configuration set) and the SES account suppression list. The tab's JSON endpoints
return that payload as it is. This module only shapes it for the page, and never calls AWS:

- each number once. The old page's "Bounce / Complaint" tile was the sum of two Delivery Mix rows, and the Mix's
  "Sent" and "Delivered" rows repeated two tiles, so the tab shows the totals as tiles and only the error types
  (and the delays, which are not errors) as a breakdown;
- the daily series in the shape the page's chart script (``mail/js/email-monitoring.js``) draws, every day of the
  window present, with a data table;
- the one notice that says why figures are missing, in the order the old page decided it: another provider is
  active, SES is not configured, CloudWatch cannot be read, the suppression list cannot be read.
"""

from datetime import date

from apps.mail.services.campaign.dashboard import DEFAULT_WINDOW_DAYS

# The ranges the tab offers (``?days=``, trailing days), as the Delivery Dashboard did; any other value reads the
# default.
WINDOWS = {
    7: ("Last 7 days", "7d"),
    90: ("Last 3 months", "3mo"),
    DEFAULT_WINDOW_DAYS: ("Last 6 months", "6mo"),
    365: ("Last 12 months", "12mo"),
}
ERROR_TYPES = (
    ("bounces", "Bounces"),
    ("complaints", "Complaints"),
    ("rejected", "Rejected by SES"),
    ("failed", "Rendering failures"),
)
DAILY_SERIES = (("attempts", "Attempts"), ("problems", "Errors"))
DEFAULT_RECIPIENT_ACTIONS = ("ses:ListSuppressedDestinations",)


def window_days(params) -> int:
    """The window a request asks for (``days``), or the default when it is missing or not one of ``WINDOWS``."""
    try:
        days = int(params.get("days", DEFAULT_WINDOW_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_DAYS
    return days if days in WINDOWS else DEFAULT_WINDOW_DAYS


def window(days: int) -> dict:
    label, short = WINDOWS.get(days, WINDOWS[DEFAULT_WINDOW_DAYS])
    return {"days": days, "label": label, "short": short}


def window_options(selected: int) -> list[dict]:
    return [{**window(days), "selected": days == selected} for days in WINDOWS]


def error_types(summary: dict) -> list[dict]:
    """The SES errors by type, as a ranked bar list (each count as a share of the largest)."""
    rows = [{"key": key, "label": label, "count": int(summary.get(key) or 0)} for key, label in ERROR_TYPES]
    largest = max(row["count"] for row in rows)
    return [{**row, "share": round(100 * row["count"] / largest, 1) if largest else 0} for row in rows]


def daily_series(daily: list[dict]) -> dict:
    """``{"names", "labels", "display", "series", "table"}`` for the chart script, one bucket per day of the window."""
    labels = [row["date"] for row in daily]
    display = [date.fromisoformat(day).strftime("%b %d") for day in labels]
    values = {key: [int(row.get(key) or 0) for row in daily] for key, _label in DAILY_SERIES}
    return {
        "names": [{"key": key, "label": label} for key, label in DAILY_SERIES],
        "labels": labels,
        "display": display,
        "series": values,
        "table": [
            {"label": text, "values": [values[key][position] for key, _label in DAILY_SERIES]}
            for position, text in enumerate(display)
            if any(values[key][position] for key, _label in DAILY_SERIES)
        ],
    }


def recipient_details_blocked(aws: dict) -> str:
    """Why the failed recipients are missing while the CloudWatch totals loaded (the old page's wording)."""
    code = f" AWS returned {aws['recipient_details_error_code']}." if aws.get("recipient_details_error_code") else ""
    if aws.get("recipient_details_reason") == "permission":
        actions = ", ".join(aws.get("recipient_details_required_actions") or DEFAULT_RECIPIENT_ACTIONS)
        key = aws.get("iam_key") or "the active IAM key"
        region = aws.get("region") or "the configured region"
        return (
            "CloudWatch totals are loaded, but exact failed recipient emails are blocked. "
            f"Grant {actions} to {key} in {region}.{code}"
        )
    return (
        "CloudWatch totals are loaded, but exact failed recipient emails are unavailable from the AWS SES suppression "
        f"list right now.{code}"
    )


def notice(aws: dict) -> dict | None:
    """The one notice the tab shows, or None when SES is in use and everything could be read."""
    if aws.get("provider") and aws["provider"] != "ses":
        provider = aws.get("provider_label") or aws["provider"]
        return {
            "key": "provider",
            "level": "info",
            "text": (
                f"These metrics come from AWS SES CloudWatch. The active email provider is {provider}, which reports "
                "no delivery events here; its emails are on the Overview and in the Email log, and each campaign's "
                "send status lists its recipients."
            ),
        }
    if not aws.get("configured"):
        text = "AWS SES is not fully configured. Check Notification Delivery and AWS IAM credentials before sending."
        return {"key": "unconfigured", "level": "error", "text": text}
    if not aws.get("metrics_available"):
        text = (
            "AWS CloudWatch SES metrics are unavailable. Grant cloudwatch:ListMetrics and cloudwatch:GetMetricData to "
            "the active IAM user."
        )
        return {"key": "metrics", "level": "error", "text": text}
    if not aws.get("recipient_details_available"):
        return {"key": "recipients", "level": "error", "text": recipient_details_blocked(aws)}
    return None


def _domain(address: str) -> str:
    parts = str(address or "").split("@")
    return parts[-1].lower() if len(parts) > 1 else "-"


def _reason_count(details: dict, rows: list[dict], reason: str) -> int:
    return int((details.get("reason_counts") or {}).get(reason) or sum(1 for row in rows if row["reason"] == reason))


def recipients(payload: dict, current: dict) -> dict:
    """The suppression list's rows (with their domain) and its summary, or why there are none."""
    rows = [{**row, "domain": _domain(row.get("email"))} for row in payload.get("problem_recipients") or []]
    details = payload.get("recipient_details") or {}
    total = details.get("total_count")
    if not details.get("available") and details.get("reason") == "unconfigured":
        empty = "The suppression list cannot be read: AWS SES is not configured."
    elif not details.get("available") and details.get("reason") == "permission":
        empty = (
            recipient_details_blocked(payload["aws"])
            + " CloudWatch only provides aggregate counts, not recipient email addresses."
        )
    elif not details.get("available"):
        empty = recipient_details_blocked(payload["aws"])
    else:
        empty = f"No suppressed recipient addresses found in AWS SES for {current['label'].lower()}."
    return {
        "rows": rows,
        "total": total if total is not None else len(rows),
        "bounced": _reason_count(details, rows, "BOUNCE"),
        "complained": _reason_count(details, rows, "COMPLAINT"),
        "latest": details.get("latest_seen") or "-",
        "empty": empty,
    }


def tab(payload: dict, days: int) -> dict:
    """The Amazon SES tab's context from the dashboard payload of ``days``."""
    current = window(days)
    aws = payload.get("aws") or {}
    return {
        "summary": payload["summary"],
        "aws": aws,
        "window": current,
        "windows": window_options(days),
        "notice": notice(aws),
        "error_types": error_types(payload["summary"]),
        "chart_data": {"daily": daily_series(payload.get("daily") or [])},
        "recipients": recipients(payload, current),
    }
