"""Opted-out SMS destinations: the check every send makes, and a read-only read of AWS's opted-out list.

``core`` keeps no opt-out list. The app that does (mail) registers two callables from its ``AppConfig.ready()``:
``is_opted_out(e164) -> bool``, which ``sms_send.send_text_message`` asks before anything is admitted (so every
SMS the site sends honours it: codes, the admin test SMS, campaigns, ticket texts), and ``record_refusal(e164)``,
told when AWS itself refuses a destination because it opted out (``Reason`` ``DESTINATION_PHONE_NUMBER_OPTED_OUT``).
With nothing registered every destination may be tried; AWS still refuses an opted-out one.

``read_opted_out_list`` reads AWS End User Messaging's opted-out list for the sending number: DescribePhoneNumbers
names the number's list, DescribeOptedOutNumbers pages through it. Both are read-only (IAM:
``sms-voice:DescribePhoneNumbers``, ``sms-voice:DescribeOptedOutNumbers``); nothing here changes AWS.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.core.exceptions import ImproperlyConfigured

from .credentials import resolve_aws_credentials
from .provider_outcomes import PROVIDER_OUTCOME_TRANSIENT, with_timeout
from .sms_errors import SmsDeliveryError, SmsOptedOut

logger = logging.getLogger(__name__)

OPTED_OUT_REASON = "DESTINATION_PHONE_NUMBER_OPTED_OUT"
DEFAULT_LIST_NAME = "Default"
CHECK_FAILED = "The SMS opt-out list could not be checked; nothing was sent."
_READ_RETRIES = Config(retries={"total_max_attempts": 3, "mode": "standard"})

_hooks: dict[str, Callable | None] = {"is_opted_out": None, "record_refusal": None}


def register_opt_out_list(*, is_opted_out: Callable[[str], bool], record_refusal: Callable[[str], None]) -> None:
    """Install the opt-out list's callables (once, from ``AppConfig.ready()``; the same ones again is a no-op)."""
    new = {"is_opted_out": is_opted_out, "record_refusal": record_refusal}
    if any(_hooks[name] not in (None, new[name]) for name in new):
        raise ImproperlyConfigured("An SMS opt-out list is already registered with other callables.")
    _hooks.update(new)


def refuse_if_opted_out(destination: str) -> None:
    """Raise ``SmsOptedOut`` for a destination on the opt-out list; a failed check refuses too (fail closed)."""
    check = _hooks["is_opted_out"]
    if check is None:
        return
    try:
        opted_out = check(destination)
    except Exception as exc:  # noqa: BLE001 - nothing may be sent while the list cannot be read.
        logger.exception("Could not check the SMS opt-out list")
        raise SmsDeliveryError(CHECK_FAILED, outcome=PROVIDER_OUTCOME_TRANSIENT) from exc
    if opted_out:
        raise SmsOptedOut(code="OptedOut")


def is_opted_out_refusal(exc: BaseException) -> bool:
    """True for AWS's answer that the destination opted out (the error's top-level ``Reason``)."""
    if not isinstance(exc, ClientError):
        return False
    return str((exc.response or {}).get("Reason") or "") == OPTED_OUT_REASON


def opted_out_refusal(exc: BaseException, destination: str, error: SmsDeliveryError) -> SmsDeliveryError:
    """``error`` as ``SmsOptedOut`` when AWS refused ``destination`` because it opted out (and tell the list); else
    ``error`` unchanged."""
    if not is_opted_out_refusal(exc):
        return error
    record = _hooks["record_refusal"]
    if record is not None:
        try:
            record(destination)
        except Exception:  # noqa: BLE001 - the refusal itself must still reach the caller.
            logger.exception("Could not record an SMS opt-out AWS reported")
    return SmsOptedOut(code=error.code, signal=error.rate_signal, refused_by_provider=True)


@dataclass(frozen=True)
class OptedOutNumber:
    phone_number: str
    opted_out_at: datetime | None
    #: True: the person opted out (replied STOP); False: an account admin added it; None: AWS did not say.
    end_user_opted_out: bool | None


@dataclass(frozen=True)
class OptedOutList:
    list_name: str
    numbers: tuple[OptedOutNumber, ...]
    #: Every page was read. A partial read (the page cap) may miss numbers, so it must never clear one.
    complete: bool


class OptOutListError(RuntimeError):
    """AWS could not be read: a sanitized message and AWS's error code (empty when there was no answer)."""

    def __init__(self, message: str, *, code: str = ""):
        super().__init__(message)
        self.code = code


def read_opted_out_list(
    *, origination: str, list_name: str, page_size: int, max_pages: int, timeout: float
) -> OptedOutList:
    """Read the opted-out list of ``origination`` (the sending number; blank: the first active SMS number), or of
    ``list_name`` when staff named one. Raises ``AwsCredentialsError`` (not configured) or ``OptOutListError``."""
    credentials = resolve_aws_credentials("sns")
    client = boto3.client(
        "pinpoint-sms-voice-v2",
        region_name=credentials.region,
        aws_access_key_id=credentials.access_key_id,
        aws_secret_access_key=credentials.secret_access_key,
        config=with_timeout(_READ_RETRIES, timeout),
    )
    try:
        name = list_name or _list_name_of(client, origination)
        numbers, complete = _read_pages(client, name, page_size=page_size, max_pages=max_pages)
    except ClientError as exc:
        code = str(((exc.response or {}).get("Error") or {}).get("Code") or "")
        logger.warning("Reading the SMS opted-out list failed: code=%s", code or "ClientError")
        raise OptOutListError("AWS refused to read the opted-out list.", code=code) from exc
    except BotoCoreError as exc:
        logger.warning("Reading the SMS opted-out list failed: %s", exc.__class__.__name__)
        raise OptOutListError("AWS could not be reached to read the opted-out list.") from exc
    return OptedOutList(list_name=name, numbers=tuple(numbers), complete=complete)


def _matches(number: dict, origination: str) -> bool:
    if origination:
        return origination in (number.get("PhoneNumber"), number.get("PhoneNumberId"), number.get("PhoneNumberArn"))
    # No configured number: the site sends from the first active SMS number (``sms.resolve_origination_number``).
    return number.get("Status") == "ACTIVE" and "SMS" in (number.get("NumberCapabilities") or [])


def _list_name_of(client, origination: str) -> str:
    """The opt-out list the sending number uses (AWS's ``Default`` when it is not one of the account's numbers)."""
    next_token = None
    while True:
        response = client.describe_phone_numbers(**({"NextToken": next_token} if next_token else {}))
        for number in response.get("PhoneNumbers", []):
            if _matches(number, origination):
                return number.get("OptOutListName") or DEFAULT_LIST_NAME
        next_token = response.get("NextToken")
        if not next_token:
            return DEFAULT_LIST_NAME


def _read_pages(client, list_name: str, *, page_size: int, max_pages: int) -> tuple[list[OptedOutNumber], bool]:
    numbers, next_token = [], None
    for _page in range(max(1, max_pages)):
        kwargs = {"OptOutListName": list_name, "MaxResults": max(1, page_size)}
        if next_token:
            kwargs["NextToken"] = next_token
        response = client.describe_opted_out_numbers(**kwargs)
        for entry in response.get("OptedOutNumbers", []):
            if entry.get("OptedOutNumber"):
                numbers.append(
                    OptedOutNumber(
                        phone_number=str(entry["OptedOutNumber"]),
                        opted_out_at=entry.get("OptedOutTimestamp"),
                        end_user_opted_out=entry.get("EndUserOptedOut"),
                    )
                )
        next_token = response.get("NextToken")
        if not next_token:
            return numbers, True
    return numbers, False
