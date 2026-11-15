"""The one SendTextMessage call (AWS End User Messaging SMS), paced by the delivery-rate limiter.

Every SMS the site sends goes through ``send_text_message``: codes, the admin test SMS, campaign recipients and ticket
texts. A destination on the opt-out list (``sms_opt_outs``) is refused before anything is admitted, and one AWS refuses
as opted out is reported to that list. Each send is admitted on the ``sms_send`` channel for its
``<region>:<origination>`` identity (one message and its parts; the API quota is per account and Region, so the Region
is the cooldown group), sent once with SDK retries off, and AWS's answer is recorded (``delivery_rates.adapters.sms``).
Campaigns pass ``lane=Lane.BULK``; everything else is transactional. A caller that must admit before other work (an OTP
reserves its challenge first) passes ``admit_text``'s admission in, and releases it itself if it never sends.
"""

import logging
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from apps.core.models.base.delivery_rates import DeliveryChannel
from apps.core.services.delivery_rates import (
    Lane,
    RateDeferred,
    RateRefused,
    admit,
    held_for,
    none,
    not_now,
    ok,
    record,
    release,
    sms_identity,
    sms_parts,
    uncertain,
)
from apps.core.services.delivery_rates.adapters.sms import sms_signal
from apps.core.services.delivery_rates.rules.defaults import channel_settings

from .credentials import AwsCredentialsError, resolve_aws_credentials
from .provider_outcomes import (
    NO_PROVIDER_RETRIES,
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_TRANSIENT,
    PROVIDER_OUTCOME_UNCERTAIN,
    classify_aws_send_failure,
    with_timeout,
)
from .sms import cached_origination_number
from .sms_errors import SmsDeliveryError, SmsRateDeferred
from .sms_opt_outs import opted_out_refusal, refuse_if_opted_out

logger = logging.getLogger(__name__)

NOT_CONFIGURED = "SMS is not configured."
CREDENTIALS_MISSING = "AWS credentials are not configured."
# AWS's message type, not the delivery lane: codes and campaign texts have always gone on the transactional route.
MESSAGE_TYPE = "TRANSACTIONAL"


@dataclass(frozen=True)
class SmsSender:
    """Where the site's SMS come from: the AWS Region and the origination number or sender ID."""

    region: str
    origination: str

    @property
    def identity(self) -> str:
        return sms_identity(self.region, self.origination)


def resolve_sender(aws_config=None) -> SmsSender:
    """The active sender (the configured number, else the auto-detected one); ``SmsDeliveryError`` without one."""
    if aws_config is None:
        from apps.core.models import AWSCredentialConfig

        aws_config = AWSCredentialConfig.load()
    origination = aws_config.resolved_sms_from_number()
    if not origination:
        raise SmsDeliveryError(NOT_CONFIGURED, outcome=PROVIDER_OUTCOME_PERMANENT)
    return SmsSender(region=aws_config.region, origination=origination)


def active_rate_target() -> tuple[str, str] | None:
    """The SMS channel and identity in use (``delivery_rates.families``), or None while SMS is not set up.

    Registered for the SMS family in ``CoreConfig.ready``. It never calls AWS: the worker reads it on every claim,
    so an auto-detected number counts only once a send has cached it.
    """
    from apps.core.models import AWSCredentialConfig

    aws = AWSCredentialConfig.load()
    if not aws.is_configured:
        return None
    origination = aws.sms_from_number or cached_origination_number(aws.region)
    return (DeliveryChannel.SMS_SEND, sms_identity(aws.region, origination)) if origination else None


def admit_text(sender: SmsSender, body: str, *, lane: str = Lane.TRANSACTIONAL):
    """Take the SMS's slot: one message, its parts, and one unit of any SMS daily limit. Raises ``SmsRateDeferred``."""
    try:
        return admit(
            DeliveryChannel.SMS_SEND, sender.identity, lane=lane, budget_cost=1, message_cost=1, parts=sms_parts(body)
        )
    except RateDeferred as exc:
        raise SmsRateDeferred(exc) from None
    except RateRefused as exc:
        raise SmsDeliveryError(str(exc), outcome=PROVIDER_OUTCOME_PERMANENT) from None


def _client(sender: SmsSender):
    try:
        credentials = resolve_aws_credentials("sns")
    except AwsCredentialsError as exc:
        raise SmsDeliveryError(CREDENTIALS_MISSING, outcome=PROVIDER_OUTCOME_PERMANENT) from exc
    return boto3.client(
        "pinpoint-sms-voice-v2",
        region_name=sender.region,
        aws_access_key_id=credentials.access_key_id,
        aws_secret_access_key=credentials.secret_access_key,
        config=with_timeout(NO_PROVIDER_RETRIES, channel_settings(DeliveryChannel.SMS_SEND)["request_timeout_seconds"]),
    )


def send_text_message(
    destination: str,
    body: str,
    *,
    lane: str = Lane.TRANSACTIONAL,
    sender: SmsSender | None = None,
    admission=None,
    before_provider_call=None,
) -> str:
    """Send one SMS to ``destination`` (E.164) and return AWS's MessageId.

    Raises ``SmsRateDeferred`` (held back, certainly not sent) or ``SmsDeliveryError``. ``before_provider_call``
    runs after the admission, just before the provider call (a job records the call there, or refuses it).
    """
    sender = sender or resolve_sender()
    try:
        refuse_if_opted_out(destination)
        client = _client(sender)
    except SmsDeliveryError:
        if admission is not None:
            _settle(admission, None)
        raise
    admission = admission or admit_text(sender, body, lane=lane)
    reached = False
    try:
        if before_provider_call is not None:
            before_provider_call()
        reached = True
        response = client.send_text_message(
            DestinationPhoneNumber=destination,
            OriginationIdentity=sender.origination,
            MessageBody=body,
            MessageType=MESSAGE_TYPE,
        )
    except (ClientError, BotoCoreError) as exc:
        raise _provider_error(exc, admission, destination) from exc
    except BaseException:
        # The caller's callback refused (a lost job claim), or the call failed unexpectedly.
        _settle(admission, uncertain("exception") if reached else None)
        raise
    _settle(admission, ok())
    return response.get("MessageId", "")


def _provider_error(exc: Exception, admission, destination: str) -> SmsDeliveryError:
    """Record AWS's answer and return the sanitized error: an answer that only says "not now" is transient."""
    outcome, message = classify_aws_send_failure(exc, provider="SMS")
    code = str(((getattr(exc, "response", None) or {}).get("Error") or {}).get("Code") or "")
    logger.warning("send_text_message failed: code=%s", code or exc.__class__.__name__)
    signal = sms_signal(exc)
    if signal is None:
        signal = uncertain("unconfirmed") if outcome == PROVIDER_OUTCOME_UNCERTAIN else none("unreachable")
    _settle(admission, signal)
    retry_after = None
    if not_now(signal):
        outcome, retry_after = PROVIDER_OUTCOME_TRANSIENT, _held_for(admission)
    error = SmsDeliveryError(message, outcome=outcome, retry_after=retry_after, code=code, signal=signal)
    return opted_out_refusal(exc, destination, error)


def _settle(admission, signal) -> None:
    """Record ``signal`` (None: AWS was never reached, so give the slot back). A failure to record is logged, never
    raised: the message's own outcome is already decided."""
    try:
        if signal is None:
            release(admission)
        else:
            record(admission, signal)
    except Exception:  # noqa: BLE001 - the delivery outcome must reach the caller unchanged.
        logger.exception("Could not record the delivery-rate outcome of an SMS")


def _held_for(admission) -> int | None:
    try:
        return held_for(admission)
    except Exception:  # noqa: BLE001 - only the wait hint is lost.
        logger.exception("Could not read how long SMS delivery is held back")
        return None
