from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from apps.authn.models import SendDestinationState, SendQuotaWindow, SendVerificationRequest

from .config import SendVerificationSettings
from .constants import EMAIL_CHANNEL, SMS_CHANNEL
from .exceptions import SendThrottled
from .metrics import emit


def _day_window_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _lock_destination(kind: str, destination: str) -> SendDestinationState:
    state, _created = SendDestinationState.objects.get_or_create(
        destination_kind=kind,
        destination_normalized=destination,
    )
    return SendDestinationState.objects.select_for_update().get(pk=state.pk)


def _lock_quota_window(*, kind: str, scope_key: str, window_started_at: datetime) -> SendQuotaWindow:
    window, _created = SendQuotaWindow.objects.get_or_create(
        kind=kind,
        scope_key=scope_key,
        window_started_at=window_started_at,
        defaults={"reserved_count": 0},
    )
    return SendQuotaWindow.objects.select_for_update().get(pk=window.pk)


def reserve_send_quotas(
    *,
    config: SendVerificationSettings,
    channel: str,
    destination_kind: str,
    destination_normalized: str,
    now: datetime | None = None,
) -> None:
    """Lock destination and quota rows in stable order, then reserve.

    SMS hourly caps stay on PhoneVerificationChallenge.send_reserved_at so this
    path does not double-charge the destination hour for SMS.
    """
    now = now or timezone.now()
    destination_state = _lock_destination(destination_kind, destination_normalized)
    daily_window = None
    if channel == SMS_CHANNEL:
        if not config.sms_daily_limit:
            from .constants import MODE_ENFORCE
            from .exceptions import SendVerificationUnavailable

            if config.mode == MODE_ENFORCE:
                raise SendVerificationUnavailable(
                    "SMS sending is paused until a daily reservation limit is configured."
                )
        else:
            daily_window = _lock_quota_window(
                kind=SendQuotaWindow.Kind.SMS_DAILY,
                scope_key="sms:global",
                window_started_at=_day_window_start(now),
            )

    cooldown = timedelta(seconds=config.destination_cooldown_seconds)
    if (
        config.destination_cooldown_seconds
        and destination_state.last_reserved_at
        and now - destination_state.last_reserved_at < cooldown
    ):
        retry_after = int((cooldown - (now - destination_state.last_reserved_at)).total_seconds()) + 1
        emit("quota_cooldown", destination=destination_normalized, channel=channel)
        raise SendThrottled("Please wait before requesting another code.", retry_after=max(retry_after, 1))

    if channel == EMAIL_CHANNEL:
        hourly = SendVerificationRequest.objects.filter(
            destination_kind=destination_kind,
            destination_normalized=destination_normalized,
            quota_reserved=True,
            reserved_at__gte=now - timedelta(hours=1),
        ).count()
        if hourly >= config.destination_hourly_limit:
            emit("quota_destination_hourly", destination=destination_normalized, channel=channel)
            raise SendThrottled(retry_after=3600)

    if daily_window is not None and daily_window.reserved_count >= int(config.sms_daily_limit):
        emit("quota_sms_daily", destination=destination_normalized, channel=channel)
        raise SendThrottled("The SMS sending budget for today has been reached.", retry_after=3600)

    destination_state.last_reserved_at = now
    destination_state.save(update_fields=["last_reserved_at", "updated_at"])
    if daily_window is not None:
        SendQuotaWindow.objects.filter(pk=daily_window.pk).update(reserved_count=daily_window.reserved_count + 1)


def destination_hourly_count(*, destination_kind: str, destination_normalized: str, now=None) -> int:
    now = now or timezone.now()
    return SendVerificationRequest.objects.filter(
        destination_kind=destination_kind,
        destination_normalized=destination_normalized,
        quota_reserved=True,
        reserved_at__gte=now - timedelta(hours=1),
    ).count()
