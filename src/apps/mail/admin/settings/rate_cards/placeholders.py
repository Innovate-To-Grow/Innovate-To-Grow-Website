from apps.core.models import DeliveryRatePolicy
from apps.core.models.base.delivery_rates import limits_from_configuration
from apps.core.services.delivery_rates import channel_info
from apps.core.services.delivery_rates.rules.channels import smtp_host
from apps.core.services.delivery_rates.rules.defaults import channel_settings, section
from apps.core.services.delivery_rates.status_text import clock, number

Channel = DeliveryRatePolicy.Channel


def placeholders(policy, state) -> dict[str, str]:
    """What a blank Advanced field means: the reported, documented or default value that applies instead."""
    spec = channel_settings(policy.channel)
    provider, unit = channel_info(policy.channel).provider, policy.unit.label
    found = {"provider_limit": _rate_placeholder(spec, state, provider, unit)}
    if "parts_limit" in spec:
        found["parts_limit"] = _parts_placeholder(spec, state, provider)
    for name in ("daily_limit", "daily_message_limit", "daily_external_limit"):
        if name in spec:
            found[name] = _count_placeholder(name, policy.channel, state, provider, "24 h")
    for name in ("hourly_external_limit", "hourly_internal_limit"):
        if name in spec:
            found[name] = _count_placeholder(name, policy.channel, state, provider, "hour")
    if "transactional_reserve" in spec:
        found["transactional_reserve"] = f"{number(section('lanes')['transactional_reserve'])} (the default)"
    if "internal_domain" in spec:
        found["internal_domain"] = "Blank: every recipient counts as external"
    return found


def _when(state) -> str:
    return clock(state.discovered_at, seconds=False) if state.discovered_at else ""


def _rate_placeholder(spec, state, provider: str, unit: str) -> str:
    if state is not None and state.discovered_rate:
        when = f" ({_when(state)})" if state.discovered_at else ""
        return f"{provider} reports {number(state.discovered_rate)} {unit}{when}"
    if spec["provider_limit"] is not None:
        return f"{number(spec['provider_limit'])} {unit} {_ceiling_source(spec)}"
    return f"Unknown: Smart rate uses the {number(spec['fallback_rate'])} {unit} app default"


def _ceiling_source(spec) -> str:
    return "on the Microsoft Graph configuration" if limits_from_configuration(spec) else "documented"


def _parts_placeholder(spec, state, provider: str) -> str:
    if state is not None and state.discovered_parts_rate:
        detail = ", ".join(filter(None, [(state.discovered_extra or {}).get("number_type"), _when(state)]))
        return f"{provider} reports {number(state.discovered_parts_rate)} MPS" + (f" ({detail})" if detail else "")
    return f"Unknown: Smart rate assumes {number(spec['parts_fallback_rate'])} parts/sec"


def _count_placeholder(name: str, channel: str, state, provider: str, window: str) -> str:
    spec = channel_settings(channel)
    extra = (state.discovered_extra or {}) if state is not None else {}
    if name == "daily_limit" and state is not None and state.discovered_at and "max_24_hour_send" in extra:
        if state.discovered_daily:
            return f"{provider} reports {state.discovered_daily:,} per 24 h"
        return f"{provider} reports no 24-hour limit"
    if name == "daily_limit" and channel == Channel.SES_SEND:
        # SES reports its 24-hour quota (GetAccount Max24HourSend) rather than documenting one.
        return f"Not read yet: {provider} reports it"
    host = smtp_host(state.identity) if state is not None and state.identity else ""
    profile = spec.get("host_profiles", {}).get(host) or {}
    if profile.get(name):
        return f"{profile[name]:,} per {window} documented for {host}"
    if spec.get(name) is not None:
        return f"{spec[name]:,} per {window} {_ceiling_source(spec)}"
    if limits_from_configuration(spec):
        return "None: blank on the Microsoft Graph configuration"
    return "None documented"
