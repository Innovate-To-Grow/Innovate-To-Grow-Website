from __future__ import annotations

from datetime import timedelta

from botocore.exceptions import ClientError
from django.conf import settings
from django.utils import timezone

from apps.core.models import AWSCredentialConfig, EmailServiceConfig

from ..delivery.pacing import email_send_rate_line

DEFAULT_WINDOW_DAYS = 183


SUPPRESSION_REASONS = ("BOUNCE", "COMPLAINT")


PERMISSION_ERROR_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "AuthorizationError",
    "InvalidClientTokenId",
    "SignatureDoesNotMatch",
    "UnauthorizedOperation",
    "UnrecognizedClientException",
}


# Exception details never reach the JSON payload: the dashboard only sees these
# fixed messages (keyed by reason) plus an allowlisted error code, while the
# full exception text goes to the server log.
PUBLIC_ERROR_MESSAGES = {
    "permission": "The configured AWS credentials are missing the required SES suppression-list permissions.",
    "aws_error": "AWS returned an error while reading the SES suppression list.",
    "error": "An unexpected error occurred while reading the SES suppression list.",
}


def _list_suppressed_rows(client, start, end) -> list[dict]:
    rows = []
    kwargs = {
        "Reasons": list(SUPPRESSION_REASONS),
        "StartDate": start,
        "EndDate": end,
        "PageSize": 100,
    }
    while True:
        page = client.list_suppressed_destinations(**kwargs)
        rows.extend(_suppressed_destination_row(item) for item in page.get("SuppressedDestinationSummaries", []))
        next_token = page.get("NextToken")
        if not next_token:
            return rows
        kwargs["NextToken"] = next_token


def _preferred_dimension_groups():
    groups = [("CloudWatch account SES metrics", [[]])]
    configuration_set = _configuration_set_name()
    if configuration_set:
        groups.append(
            (
                f"CloudWatch SES configuration set: {configuration_set}",
                [[{"Name": "ConfigurationSet", "Value": configuration_set}]],
            )
        )
    return groups


def _configuration_set_name() -> str:
    return (getattr(settings, "SES_CONFIGURATION_SET_NAME", "") or "").strip()


def _suppressed_destination_row(item: dict) -> dict:
    reason = item.get("Reason", "")
    email = item.get("EmailAddress", "")
    last_seen = item.get("LastUpdateTime")
    status = "bounced" if reason == "BOUNCE" else "complained" if reason == "COMPLAINT" else "failed"
    label = "Bounced" if reason == "BOUNCE" else "Complained" if reason == "COMPLAINT" else reason.title()
    return {
        "email": email,
        "name": "",
        "source": "AWS SES Suppression List",
        "context": "Account-level suppression",
        "status": status,
        "label": label,
        "reason": reason or "Suppressed by SES",
        "last_seen": _display_dt(last_seen),
        "count": 1,
        "_last_seen_sort": last_seen or timezone.now() - timedelta(days=36500),
    }


def _recipient_reason_counts(rows: list[dict]) -> dict:
    counts = dict.fromkeys(SUPPRESSION_REASONS, 0)
    for row in rows:
        reason = row.get("reason")
        if reason:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _recipient_details_meta(
    available: bool,
    reason: str,
    *,
    error_code: str = "",
    required_actions: tuple[str, ...] = (),
) -> dict:
    return {
        "available": available,
        "reason": reason,
        "source": "AWS SES account suppression list",
        "count": 0,
        "error_code": error_code,
        "error_message": PUBLIC_ERROR_MESSAGES.get(reason, ""),
        "required_actions": list(required_actions),
        "returned_count": 0,
        "total_count": 0,
        "truncated": False,
        "limit": None,
        "reason_counts": {},
        "latest_seen": "-",
        "window_days": DEFAULT_WINDOW_DAYS,
    }


def _aws_meta(metric_payload: dict, recipient_details: dict) -> dict:
    email_config = EmailServiceConfig.load()
    aws_config = AWSCredentialConfig.load()
    configured = email_config.ses_configured
    return {
        "configured": configured,
        "provider": email_config.provider,
        "provider_label": email_config.get_provider_display(),
        "email_config": email_config.name,
        "aws_config": aws_config.name,
        "region": aws_config.region,
        "source_address": email_config.source_address,
        "send_rate": email_send_rate_line(),
        "iam_key": "Secrets Manager"
        if aws_config.credentials_secret_arn
        else (f"...{aws_config.access_key_id[-4:]}" if aws_config.access_key_id else "Not configured"),
        "metrics_available": metric_payload["metrics"]["available"],
        "metrics_reason": metric_payload["metrics"]["reason"],
        "metrics_source": metric_payload["metrics"]["source"],
        "recipient_details_available": recipient_details["available"],
        "recipient_details_reason": recipient_details["reason"],
        "recipient_details_error_code": recipient_details.get("error_code", ""),
        "recipient_details_error_message": recipient_details.get("error_message", ""),
        "recipient_details_required_actions": recipient_details.get("required_actions", []),
    }


def _display_dt(value) -> str:
    if not value:
        return "-"
    return timezone.localtime(value).strftime("%b %d, %H:%M")


def _client_error_code(exc: ClientError) -> str:
    return exc.response.get("Error", {}).get("Code", "")


def _client_error_reason(exc: ClientError) -> str:
    code = _client_error_code(exc)
    return "permission" if code in PERMISSION_ERROR_CODES or "denied" in code.lower() else "aws_error"
