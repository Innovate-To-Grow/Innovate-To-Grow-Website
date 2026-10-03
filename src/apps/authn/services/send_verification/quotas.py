"""Send quotas: the per-destination cooldown and hourly cap, and the global SMS daily budget.

Two reservations, taken at two different moments:

* ``reserve_send_quotas`` runs for EVERY protected send request, in the transaction that consumes the ALTCHA proof
  and inserts the send-request row. It reserves the destination (cooldown, email hourly cap), whether or not the
  request ends up sending anything.
* ``reserve_sms_dispatch`` runs only when an SMS is about to be handed to the provider
  (``start_phone_verification``). It reserves one unit of the global SMS daily budget, so the budget counts
  provider calls and nothing else: a request that sends no SMS (a password reset for a number without an account,
  a number over its own hourly cap) costs nothing.

Both counters live in PostgreSQL rows locked with ``SELECT ... FOR UPDATE``; nothing is keyed on the client IP.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from apps.authn.models import SendDestinationState, SendQuotaWindow, SendVerificationRequest

from .config import SendVerificationSettings, load_settings
from .constants import EMAIL_CHANNEL, MODE_ENFORCE, SMS_CHANNEL
from .exceptions import SendThrottled, SendVerificationUnavailable
from .metrics import emit

SMS_DAILY_SCOPE = "sms:global"
SMS_BUDGET_SPENT_DETAIL = "The SMS sending budget for today has been reached."
# The budget window is the UTC day; an hour is a truthful "not before" without promising the exact reset.
SMS_BUDGET_RETRY_AFTER = 3600


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


def _require_sms_budget_when_enforced(config: SendVerificationSettings) -> None:
    """Enforce mode never sends SMS without a daily budget: an unset limit is "not calibrated", not "unlimited"."""
    if not config.sms_daily_limit and config.mode == MODE_ENFORCE:
        raise SendVerificationUnavailable("SMS sending is paused until a daily reservation limit is configured.")


def _sms_budget_spent(config: SendVerificationSettings, now: datetime) -> bool:
    """Whether today's SMS budget is already fully reserved. A plain read: no lock, no row created."""
    if not config.sms_daily_limit:
        return False
    reserved = (
        SendQuotaWindow.objects.filter(
            kind=SendQuotaWindow.Kind.SMS_DAILY,
            scope_key=SMS_DAILY_SCOPE,
            window_started_at=_day_window_start(now),
        )
        .values_list("reserved_count", flat=True)
        .first()
    )
    return reserved is not None and reserved >= int(config.sms_daily_limit)


def _sms_budget_spent_error(destination: str) -> SendThrottled:
    emit("quota_sms_daily", destination=destination, channel=SMS_CHANNEL)
    return SendThrottled(SMS_BUDGET_SPENT_DETAIL, retry_after=SMS_BUDGET_RETRY_AFTER)


def reserve_send_quotas(
    *,
    config: SendVerificationSettings,
    channel: str,
    destination_kind: str,
    destination_normalized: str,
    now: datetime | None = None,
    refuse_spent_sms_budget: bool = False,
) -> None:
    """Lock the destination row, then reserve its cooldown (and, for email, its hourly cap).

    SMS hourly caps stay on PhoneVerificationChallenge.send_reserved_at so this
    path does not double-charge the destination hour for SMS.

    The SMS daily budget is NOT reserved here (see ``reserve_sms_dispatch``). ``refuse_spent_sms_budget`` only adds
    an early, read-only refusal for a request that is certain to send an SMS: when the budget is already spent it
    answers the same ``send_throttled`` the dispatch would, before the proof, the cooldown or any row is used up.
    Callers whose answer must not depend on whether an SMS is sent (password reset) leave it off.
    """
    now = now or timezone.now()
    destination_state = _lock_destination(destination_kind, destination_normalized)
    if channel == SMS_CHANNEL:
        _require_sms_budget_when_enforced(config)

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

    if refuse_spent_sms_budget and channel == SMS_CHANNEL and _sms_budget_spent(config, now):
        raise _sms_budget_spent_error(destination_normalized)

    destination_state.last_reserved_at = now
    destination_state.save(update_fields=["last_reserved_at", "updated_at"])


def reserve_sms_dispatch(*, destination: str, now: datetime | None = None) -> None:
    """Reserve one unit of the global SMS daily budget for an SMS that is about to be handed to the provider.

    Call it inside the transaction that records the send (``start_phone_verification`` does, as that transaction's
    last statement) and call the provider only after that transaction has committed:

    * the budget row is locked ``FOR UPDATE`` and re-read under the lock, so concurrent sends are counted one after
      another and the last unit cannot be spent twice;
    * the unit is committed before the provider is called, so a crash, a timeout or a provider error can never
      leave an SMS sent but uncounted. It is never released: a failed or uncertain call keeps it;
    * a spent budget raises ``SendThrottled`` and the caller's transaction rolls back, so nothing is stored or sent.

    No daily limit configured means no budget to reserve (enforce mode refuses instead; observe mode is then bounded
    only per number, with the per-IP SMS fallback throttle as a speed bump, see ``sms_request_throttles``).
    """
    config = load_settings()
    _require_sms_budget_when_enforced(config)
    if not config.sms_daily_limit:
        return
    window = _lock_quota_window(
        kind=SendQuotaWindow.Kind.SMS_DAILY,
        scope_key=SMS_DAILY_SCOPE,
        window_started_at=_day_window_start(now or timezone.now()),
    )
    if window.reserved_count >= int(config.sms_daily_limit):
        raise _sms_budget_spent_error(destination)
    SendQuotaWindow.objects.filter(pk=window.pk).update(reserved_count=window.reserved_count + 1)


def destination_hourly_count(*, destination_kind: str, destination_normalized: str, now=None) -> int:
    now = now or timezone.now()
    return SendVerificationRequest.objects.filter(
        destination_kind=destination_kind,
        destination_normalized=destination_normalized,
        quota_reserved=True,
        reserved_at__gte=now - timedelta(hours=1),
    ).count()
