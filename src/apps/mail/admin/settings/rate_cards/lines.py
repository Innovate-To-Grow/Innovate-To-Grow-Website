from apps.core.services.delivery_rates import channel_info
from apps.core.services.delivery_rates.runtime import context
from apps.core.services.delivery_rates.status.status_text import age, clock, number
from apps.mail.admin.settings.rate_cards.placeholders import Channel


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
