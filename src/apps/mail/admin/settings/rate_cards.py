"""The cards of Mail → Delivery Rates: each channel's live status (from ``delivery_rates.snapshot``), the
placeholders of its blank Advanced fields and what the provider reported, grouped as the page shows them.

The status lines come from the limiter's own snapshot, the same lines the overview, the dashboard and the campaign
send estimate show; nothing here computes a rate.
"""

from dataclasses import dataclass

from django.db.models import F
from django.urls import reverse

from apps.core.models import DeliveryRatePolicy, DeliveryRateState, EmailServiceConfig
from apps.core.models.base.delivery_rates import limits_from_configuration
from apps.core.services.delivery_rates import Family, active_target, channel_info
from apps.core.services.delivery_rates.rules.channels import smtp_host
from apps.core.services.delivery_rates.rules.defaults import channel_settings, section
from apps.core.services.delivery_rates.runtime import context
from apps.core.services.delivery_rates.status_text import age, clock, number

Channel = DeliveryRatePolicy.Channel
Provider = EmailServiceConfig.Provider

# The sending channel of each email provider (each provider's ``rate_channel``).
EMAIL_CHANNELS = {
    Provider.GRAPH: Channel.GRAPH_SEND,
    Provider.SES: Channel.SES_SEND,
    Provider.SMTP: Channel.SMTP_SEND,
    Provider.GMAIL: Channel.GMAIL_API_SEND,
}
SMS_CHANNELS = (Channel.SMS_SEND,)
INBOX_CHANNELS = (Channel.GRAPH_READ, Channel.GMAIL_IMAP)
CARD_NOTES = {
    Channel.GMAIL_API_SEND: (
        "Google's daily limits are per Google account and include mail people send from that account in Gmail, "
        "which the site cannot see. Accepted mail may be dropped near the limit, so the site stops at the headroom."
    ),
}
ACTIONS = {
    "check": "Check provider limits now",
    "reset": "Reset Smart rate",
    "resume": "Resume sending",
}


@dataclass(frozen=True)
class CardAction:
    name: str
    label: str
    url: str
    form_id: str
    # Resume sending is shown only while a cooldown or breaker holds the channel (the status refresh toggles it).
    hidden: bool = False


@dataclass(frozen=True)
class RateCard:
    channel: str
    label: str
    form: object
    status: dict
    reported: tuple[str, ...]
    note: str
    actions: tuple[CardAction, ...]
    manual_locked: bool
    advanced_open: bool


def in_use_identities() -> dict[str, str]:
    """The identity each sending family uses now, by channel (email and SMS)."""
    found = {}
    for family in (Family.EMAIL, Family.SMS):
        target = active_target(family)
        if target is not None:
            found[target.channel] = target.identity
    return found


def primary_states(in_use: dict[str, str]) -> dict[str, DeliveryRateState]:
    """Per channel, the state the Advanced placeholders and the provider's report describe: the identity in use
    (unsaved when it has not sent yet), else the one read or used last."""
    found = {}
    for channel in Channel.values:
        rows = DeliveryRateState.objects.filter(channel=channel)
        identity = in_use.get(channel)
        state = rows.filter(identity=identity).first() if identity else None
        if state is None and identity:
            state = DeliveryRateState(channel=channel, identity=identity)
        found[channel] = state or rows.order_by(F("discovered_at").desc(nulls_last=True), "-updated_at").first()
    return found


def identity_label(channel: str, identity: str) -> str:
    if not identity:
        return ""
    if channel == Channel.SES_SEND:
        return f"AWS Region {identity.partition(':')[2]}"
    if channel == Channel.SMS_SEND:
        region, _, origination = identity.partition(":")
        return f"{origination} ({region})"
    return identity


def status_payload(status, in_use: dict[str, str]) -> dict:
    """One channel's live status, as the page renders it and ``rates/status/`` returns it."""
    current = in_use.get(status.channel)
    identities = sorted(status.identities, key=lambda item: item.identity != current)
    return {
        "channel": status.channel,
        "smart_enabled": status.smart_enabled,
        "held": any(item.cooldown_until is not None or item.breaker_open for item in status.identities),
        "identities": [
            {
                "identity": item.identity,
                "label": identity_label(status.channel, item.identity),
                "in_use": bool(current) and item.identity == current,
                "lines": list(item.lines),
                "warnings": list(item.warnings),
            }
            for item in identities
        ],
    }


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


def reported_lines(state) -> tuple[str, ...]:
    """The provider's last report for the identity, read-only (SES GetAccount; AWS SMS number and spend limit)."""
    if state is None or state.discovered_at is None or not channel_info(state.channel).discovers:
        return ()
    extra = state.discovered_extra or {}
    read = f"Read {age(context.clock() - state.discovered_at)} ago ({clock(state.discovered_at, seconds=False)})"
    if state.channel == Channel.SES_SEND:
        lines = _ses_lines(state, extra)
        if extra.get("api"):
            read += f" through {extra['api']}"
    else:
        lines = _sms_lines(state, extra)
    return (read, *lines)


def _yes_no(value) -> str:
    return "unknown" if value is None else ("yes" if value else "no")


def _ses_lines(state, extra: dict) -> list[str]:
    daily = extra.get("max_24_hour_send")
    lines = [
        f"MaxSendRate: {number(state.discovered_rate)} recipients/sec" if state.discovered_rate else "",
        f"Max24HourSend: {'no limit' if daily is not None and daily < 0 else number(daily)}"
        if daily is not None
        else "",
        f"SentLast24Hours: {state.discovered_used_24h:,}" if state.discovered_used_24h is not None else "",
        f"EnforcementStatus: {extra['enforcement_status']}" if extra.get("enforcement_status") else "",
        f"Sending enabled: {_yes_no(extra.get('sending_enabled'))}",
        f"Production access: {_yes_no(extra.get('production_access'))}",
    ]
    return [line for line in lines if line]


def _sms_lines(state, extra: dict) -> list[str]:
    caps = extra.get("daily_message_caps") or {}
    spend, spend_max = extra.get("spend_limit"), extra.get("spend_max")
    lines = [
        f"NumberType: {extra['number_type']}" if extra.get("number_type") else "",
        f"RateLimits (SMS): {number(state.discovered_parts_rate)} parts/sec" if state.discovered_parts_rate else "",
        "DailyMessageCaps: " + ", ".join(f"{name} {value:,}" for name, value in caps.items()) if caps else "",
        f"Text spend limit: USD {spend:,}" + (f" (maximum USD {spend_max:,})" if spend_max else "")
        if spend is not None
        else "",
    ]
    return [line for line in lines if line]


def _actions(channel: str, held: bool) -> tuple[CardAction, ...]:
    names = [name for name in ACTIONS if name != "check" or channel_info(channel).discovers]
    return tuple(
        CardAction(
            name=name,
            label=ACTIONS[name],
            url=reverse("admin:mail_delivery_rates_action", args=[channel, name]),
            form_id=f"rate-action-{channel}-{name}",
            hidden=name == "resume" and not held,
        )
        for name in names
    )


def build_card(form, status, state, in_use: dict[str, str]) -> RateCard:
    payload = status_payload(status, in_use)
    locked = form.lock_manual_rate()
    advanced_open = any(bound.errors for bound in form.advanced_fields())
    return RateCard(
        channel=status.channel,
        label=status.label,
        form=form,
        status=payload,
        reported=reported_lines(state),
        note=CARD_NOTES.get(status.channel, ""),
        actions=_actions(status.channel, payload["held"]),
        manual_locked=locked,
        advanced_open=advanced_open,
    )


def card_groups(cards: dict[str, RateCard], provider: str) -> dict:
    """Email sending (the selected provider first, the others under "Not in use"), SMS and Inbox reading."""
    selected = EMAIL_CHANNELS.get(provider)
    unused = [cards[channel] for channel in EMAIL_CHANNELS.values() if channel != selected]
    return {
        "email_selected": cards.get(selected),
        "email_unused": unused,
        "email_unused_open": any(card.form.errors for card in unused),
        "sms_cards": [cards[channel] for channel in SMS_CHANNELS],
        "inbox_cards": [cards[channel] for channel in INBOX_CHANNELS],
    }
