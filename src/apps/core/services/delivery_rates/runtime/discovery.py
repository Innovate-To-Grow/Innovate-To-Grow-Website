"""Provider limit discovery: SES reports its send rate and 24-hour quota, AWS SMS its number's message parts per
second and the monthly spend limit. Smart rate bounds itself by the last successful read, whatever its age.

One process wins each due read (the admission holding the row lock, or a compare-and-set for the worker, page
loads and "Check provider limits now") and calls AWS outside any transaction. A send never waits for it: an
admission that finds discovery due starts it in the background after its commit. A failed read keeps every
last-known value and records the error for the status line.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q

from apps.core.models import AWSCredentialConfig, DeliveryRateState
from apps.core.models.base.delivery_rates import DeliveryChannel
from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials
from apps.core.services.aws.quotas import QuotaReadError, read_ses_account, read_sms_limits
from apps.core.services.helpers.in_process import start_in_process_task

from ..rules.channels import cooldown_group, ses_identity
from ..rules.defaults import channel_settings, rate_spec, section
from ..rules.signals import Reason, Scope
from . import context
from .breaker import close_breaker, open_breaker

logger = logging.getLogger(__name__)


class DiscoveryUnavailable(RuntimeError):
    """The identity cannot be read now (not the active account, no credentials); safe to show."""


@dataclass(frozen=True)
class Discovered:
    rate: float | None = None
    parts_rate: float | None = None
    # SES only: the 24-hour quota (None: no limit) and what was sent in the last 24 hours.
    reports_daily: bool = False
    daily: int | None = None
    used_24h: int | None = None
    sending_enabled: bool | None = None
    spend_limit: int | None = None
    extra: dict = field(default_factory=dict)
    warning: str = ""


def _timeout() -> float:
    return float(section("discovery")["timeout_seconds"])


def _read_ses(identity: str) -> Discovered:
    config = AWSCredentialConfig.load()
    creds = resolve_aws_credentials("ses", config=config)
    if ses_identity(config.pk, creds.region) != identity:
        raise DiscoveryUnavailable("not the active AWS account")
    account = read_ses_account(creds, timeout=_timeout())
    daily = account.max_24_hour_send
    return Discovered(
        rate=account.max_send_rate,
        reports_daily=True,
        daily=None if daily is None or daily < 0 else int(daily),
        used_24h=None if account.sent_last_24_hours is None else int(account.sent_last_24_hours),
        sending_enabled=account.sending_enabled,
        extra={
            "max_24_hour_send": daily,
            "sending_enabled": account.sending_enabled,
            "enforcement_status": account.enforcement_status,
            "production_access": account.production_access,
            "api": account.api,
        },
    )


def _read_sms(identity: str) -> Discovered:
    region, _, origination = identity.partition(":")
    creds = resolve_aws_credentials("sns")
    if creds.region != region or not origination:
        raise DiscoveryUnavailable("not the active AWS account and Region")
    limits = read_sms_limits(creds, origination, timeout=_timeout())
    extra = {"number_type": limits.number_type, "daily_message_caps": limits.daily_caps}
    extra |= {"spend_limit": limits.spend_limit, "spend_max": limits.spend_max}
    return Discovered(parts_rate=limits.sms_rate, spend_limit=limits.spend_limit, extra=extra, warning=limits.warning)


READERS: dict[str, Callable[[str], Discovered]] = {
    DeliveryChannel.SES_SEND: _read_ses,
    DeliveryChannel.SMS_SEND: _read_sms,
}


def interval(channel: str) -> timedelta:
    return timedelta(seconds=channel_settings(channel)["discovery_interval_seconds"])


def claim_due(state, now: datetime) -> bool:
    """Under the admission's row lock: take a due read for this identity (True: start it after commit)."""
    if state.channel not in READERS or (state.discovery_next_at is not None and state.discovery_next_at > now):
        return False
    state.discovery_next_at = now + interval(state.channel)
    return True


def _claim(state_id, channel: str, now: datetime, *, force: bool) -> bool:
    rows = DeliveryRateState.objects.filter(pk=state_id)
    if not force:
        rows = rows.filter(Q(discovery_next_at__isnull=True) | Q(discovery_next_at__lte=now))
    return rows.update(discovery_next_at=now + interval(channel), updated_at=now) == 1


def start_refresh(channel: str, identity: str) -> None:
    """Run a claimed read on a background thread; the request that claimed it carries on."""
    start_in_process_task(_read_and_store, channel, identity, name="delivery-rate-discovery", best_effort_start=True)


def refresh_discovery(channel: str, identity: str | None = None, *, force: bool = False) -> int:
    """Read the provider limits of the channel's identities that are due (all of them with ``force``) in this
    thread; return how many were read. For the worker's maintenance, page loads and "Check provider limits now"."""
    if channel not in READERS:
        return 0
    rows = DeliveryRateState.objects.filter(channel=channel)
    if identity is not None:
        # The identity in use may not have sent yet: give it a row so its limits are known before it does.
        group = cooldown_group(channel, identity)
        DeliveryRateState.objects.get_or_create(channel=channel, identity=identity, defaults={"cooldown_group": group})
        rows = rows.filter(identity=identity)
    read = 0
    for state_id, state_identity in rows.values_list("pk", "identity"):
        if _claim(state_id, channel, context.clock(), force=force):
            _read_and_store(channel, state_identity)
            read += 1
    return read


def _read_and_store(channel: str, identity: str) -> None:
    try:
        found = READERS[channel](identity)
    except (DiscoveryUnavailable, QuotaReadError, AwsCredentialsError) as exc:
        _store(channel, identity, None, str(exc) or exc.__class__.__name__)
        return
    except Exception:  # noqa: BLE001 - a failed limit read must never escape into a send or a page.
        logger.exception("Delivery-rate discovery failed for %s", channel)
        _store(channel, identity, None, "unexpected error")
        return
    _store(channel, identity, found, found.warning)


def _store(channel: str, identity: str, found: Discovered | None, error: str) -> None:
    with transaction.atomic():
        state = DeliveryRateState.objects.select_for_update().filter(channel=channel, identity=identity).first()
        if state is None:
            return
        now = context.clock()
        state.discovery_error = error[:255]
        if found is not None:
            _apply(state, found, now)
        state.save()


def _positive(value) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) and value > 0 else None


def _apply(state, found: Discovered, now: datetime) -> None:
    previous_spend = (state.discovered_extra or {}).get("spend_limit")
    # A missing or zero rate reports nothing usable, so the last-known one stays.
    state.discovered_rate = _positive(found.rate) or state.discovered_rate
    state.discovered_parts_rate = _positive(found.parts_rate) or state.discovered_parts_rate
    if found.reports_daily:
        state.discovered_daily, state.discovered_used_24h = found.daily, found.used_24h
    state.discovered_extra = found.extra
    state.discovered_at = now
    spec = rate_spec(state.channel)
    if found.sending_enabled is False:
        open_breaker(
            state,
            reason=Reason.ACCOUNT_PAUSED,
            scope=Scope.ALL,
            seconds=spec.breaker_probe,
            spec=spec,
            now=now,
            failed_probe=False,
        )
    elif found.sending_enabled and state.breaker_reason == Reason.ACCOUNT_PAUSED:
        close_breaker(state)
    raised = found.spend_limit is not None and previous_spend is not None and found.spend_limit > previous_spend
    if state.breaker_reason == Reason.SPEND_LIMIT and raised:
        # A higher spend limit lets the next request probe now instead of at the next timed probe.
        state.breaker_retry_at = now
