"""The ``DELIVERY_RATES`` settings each rule reads, gathered per channel.

Settings are read at call time (never cached at import), so ``override_settings`` and a deploy's
``DELIVERY_RATES_OVERRIDES`` apply everywhere. Every value comes from
``config/settings/base/integrations/delivery_rates``, which documents and validates it.
"""

from dataclasses import dataclass

from django.conf import settings

from apps.core.models.base.delivery_rates import CHANNEL_UNITS

from . import tenant


def delivery_rates() -> dict:
    return settings.DELIVERY_RATES


def channel_settings(channel: str, *, configured: bool = True) -> dict:
    """The channel's seeds, ceilings and channel-specific values (pauses, discovery intervals, ...).

    Ceilings the operator entered on the channel's provider configuration (Microsoft Graph's mailbox limits) replace
    the documented ones, so every rule, status line and form reads the same numbers (``rules.tenant``). That is a
    database read; ``configured=False`` gives the settings alone (the pure-rule tests, which never touch a database).
    """
    spec = delivery_rates()["channels"][channel]
    limits = tenant.configured_limits(channel) if configured else {}
    return {**spec, **limits} if limits else spec


def section(name: str) -> dict:
    """A runtime section: controller, waits, lanes, usage, discovery or jobs."""
    return delivery_rates()[name]


def signal_patterns(adapter: str) -> dict:
    """The provider answers of one adapter (graph, ses, smtp, imap, gmail_api, sms)."""
    return delivery_rates()["signals"][adapter]


@dataclass(frozen=True)
class RateSpec:
    """Everything the precedence rule, the pacing and the controller read for one channel.

    Rates are in the channel's unit: per ``window`` seconds (60 for per-minute channels, 1 for per-second ones).
    """

    channel: str
    window: int
    # Documented provider limit: the policy field's ceiling (None: reported at runtime or unknown).
    provider_limit: float | None
    fallback_rate: float | None
    headroom: float
    burst: int
    recovery_interval: float
    backoff_initial: float
    backoff_max: float
    # Controller section.
    start_factor: float
    start_factor_without_limit: float
    decrease_factor: float
    recovery_step: float
    floor: float
    backoff_jitter: float
    retry_after_max: float
    persistent_throttle_count: int
    breaker_probe: float
    breaker_probe_max: float
    # Lanes section: campaigns use at most this share of the rate.
    bulk_share: float
    # SMS message parts (MPS): a ceiling, and what Smart rate assumes until the number's rate is reported.
    has_parts: bool = False
    parts_limit: float | None = None
    parts_fallback_rate: float | None = None
    # True when ``provider_limit`` is the limit entered on the provider configuration, not the documented one.
    tenant_limits: bool = False


def rate_spec(channel: str, *, configured: bool = True) -> RateSpec:
    spec = channel_settings(channel, configured=configured)
    controller = section("controller")
    return RateSpec(
        channel=channel,
        window=CHANNEL_UNITS[channel].per_seconds,
        provider_limit=spec["provider_limit"],
        tenant_limits=tenant.from_tenant(spec),
        fallback_rate=spec["fallback_rate"],
        headroom=spec["headroom"],
        burst=spec["burst"],
        recovery_interval=spec["recovery_interval_seconds"],
        backoff_initial=spec["backoff_initial_seconds"],
        backoff_max=spec["backoff_max_seconds"],
        start_factor=controller["start_factor"],
        start_factor_without_limit=controller["start_factor_without_limit"],
        decrease_factor=controller["decrease_factor"],
        recovery_step=controller["recovery_step"],
        floor=controller["floor"],
        backoff_jitter=controller["backoff_jitter"],
        retry_after_max=controller["retry_after_max_seconds"],
        persistent_throttle_count=controller["persistent_throttle_count"],
        breaker_probe=controller["breaker_probe_seconds"],
        breaker_probe_max=controller["breaker_probe_max_seconds"],
        bulk_share=section("lanes")["bulk_share"],
        has_parts="parts_limit" in spec,
        parts_limit=spec.get("parts_limit"),
        parts_fallback_rate=spec.get("parts_fallback_rate"),
    )
