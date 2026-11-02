"""Read the sending limits AWS reports, for Smart rate (``delivery_rates.runtime.discovery``).

- SES: sesv2 ``GetAccount`` (``ses:GetAccount``), or the v1 ``GetSendQuota`` (``ses:GetSendQuota``) when that is
  refused: maximum send rate, 24-hour quota, sent in the last 24 hours, and whether sending is enabled.
- SMS (AWS End User Messaging): the origination number's (``sms-voice:DescribePhoneNumbers``) or sender ID's
  (``sms-voice:DescribeSenderIds``) number type and send rate per capability, and the account's monthly text
  spend limit (``sms-voice:DescribeSpendLimits``). The 1-per-second SendTextMessage quota is not reported.

Every call makes one attempt (no SDK retries) with the given timeout. Failures raise ``QuotaReadError`` with only
the AWS error code and the IAM action, never a response body.
"""

import re
from dataclasses import dataclass, field

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .credentials import AwsCredentials
from .provider_outcomes import NO_PROVIDER_RETRIES, with_timeout

_CODE = re.compile(r"[A-Za-z][A-Za-z0-9.]{1,63}")
TEXT_SPEND_LIMIT = "TEXT_MESSAGE_MONTHLY_SPEND_LIMIT"


class QuotaReadError(RuntimeError):
    """A limit read failed; the message is safe to store and show ("AccessDenied: ses:GetAccount")."""


@dataclass(frozen=True)
class SesAccount:
    max_send_rate: float | None
    # -1 means no limit.
    max_24_hour_send: float | None
    sent_last_24_hours: float | None
    sending_enabled: bool | None = None
    enforcement_status: str = ""
    production_access: bool | None = None
    api: str = "sesv2"


@dataclass(frozen=True)
class SmsLimits:
    number_type: str
    # RateLimits["SMS"]: messages (parts) per second for the identity.
    sms_rate: float | None
    daily_caps: dict = field(default_factory=dict)
    spend_limit: int | None = None
    spend_max: int | None = None
    # A partial failure (the spend limit could not be read) next to otherwise good limits.
    warning: str = ""


def _client(service: str, creds: AwsCredentials, timeout: float):
    return boto3.client(
        service,
        region_name=creds.region,
        aws_access_key_id=creds.access_key_id,
        aws_secret_access_key=creds.secret_access_key,
        config=with_timeout(NO_PROVIDER_RETRIES, timeout),
    )


def _describe(exc: Exception, action: str) -> str:
    if isinstance(exc, ClientError):
        code = str((exc.response or {}).get("Error", {}).get("Code") or "")
        return f"{code if _CODE.fullmatch(code) else 'Error'}: {action}"
    return f"unreachable: {action}"


def read_ses_account(creds: AwsCredentials, *, timeout: float) -> SesAccount:
    try:
        account = _client("sesv2", creds, timeout).get_account()
    except BotoCoreError as exc:
        raise QuotaReadError(_describe(exc, "ses:GetAccount")) from None
    except ClientError as exc:
        return _read_ses_v1(creds, timeout, _describe(exc, "ses:GetAccount"))
    quota = account.get("SendQuota") or {}
    return SesAccount(
        max_send_rate=quota.get("MaxSendRate"),
        max_24_hour_send=quota.get("Max24HourSend"),
        sent_last_24_hours=quota.get("SentLast24Hours"),
        sending_enabled=account.get("SendingEnabled"),
        enforcement_status=str(account.get("EnforcementStatus") or "")[:32],
        production_access=account.get("ProductionAccessEnabled"),
    )


def _read_ses_v1(creds: AwsCredentials, timeout: float, v2_error: str) -> SesAccount:
    try:
        quota = _client("ses", creds, timeout).get_send_quota()
    except (BotoCoreError, ClientError) as exc:
        raise QuotaReadError(f"{v2_error}; {_describe(exc, 'ses:GetSendQuota')}") from None
    return SesAccount(
        max_send_rate=quota.get("MaxSendRate"),
        max_24_hour_send=quota.get("Max24HourSend"),
        sent_last_24_hours=quota.get("SentLast24Hours"),
        api="ses",
    )


def _pages(method, key: str):
    token = None
    while True:
        response = method(**({"NextToken": token} if token else {}))
        yield from response.get(key) or []
        token = response.get("NextToken")
        if not token:
            return


def _find_identity(client, origination: str) -> dict:
    if origination.startswith("+"):
        for number in _pages(client.describe_phone_numbers, "PhoneNumbers"):
            if origination in (number.get("PhoneNumber"), number.get("PhoneNumberId"), number.get("PhoneNumberArn")):
                return number
        raise QuotaReadError("origination number not found: sms-voice:DescribePhoneNumbers")
    wanted = origination.casefold()
    for sender in _pages(client.describe_sender_ids, "SenderIds"):
        if str(sender.get("SenderId") or "").casefold() == wanted or sender.get("SenderIdArn") == origination:
            return sender | {"NumberType": "SENDER_ID"}
    raise QuotaReadError("sender ID not found: sms-voice:DescribeSenderIds")


def _spend_limit(client) -> dict:
    for limit in _pages(client.describe_spend_limits, "SpendLimits"):
        if limit.get("Name") == TEXT_SPEND_LIMIT:
            return limit
    return {}


def read_sms_limits(creds: AwsCredentials, origination: str, *, timeout: float) -> SmsLimits:
    client = _client("pinpoint-sms-voice-v2", creds, timeout)
    action = "sms-voice:DescribePhoneNumbers" if origination.startswith("+") else "sms-voice:DescribeSenderIds"
    try:
        identity = _find_identity(client, origination)
    except (BotoCoreError, ClientError) as exc:
        raise QuotaReadError(_describe(exc, action)) from None
    limits = identity.get("MessagingLimits") or {}
    warning, spend = "", {}
    try:
        spend = _spend_limit(client)
    except (BotoCoreError, ClientError) as exc:
        warning = _describe(exc, "sms-voice:DescribeSpendLimits")
    caps = limits.get("DailyMessageCaps") or {}
    return SmsLimits(
        number_type=str(identity.get("NumberType") or "")[:32],
        sms_rate=(limits.get("RateLimits") or {}).get("SMS"),
        daily_caps={str(key)[:32]: value for key, value in caps.items() if isinstance(value, int)},
        spend_limit=spend.get("EnforcedLimit"),
        spend_max=spend.get("MaxLimit"),
        warning=warning,
    )
