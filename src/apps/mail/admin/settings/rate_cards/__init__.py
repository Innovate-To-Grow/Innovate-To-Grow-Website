"""The cards of Mail → Delivery Rates: each channel's live status (from ``delivery_rates.snapshot``), the
placeholders of its blank Advanced fields and what the provider reported, grouped as the page shows them.

The status lines come from the limiter's own snapshot, the same lines the overview, the dashboard and the campaign
send estimate show; nothing here computes a rate.
"""

from dataclasses import dataclass

from django.db.models import F
from django.urls import reverse

from apps.core.models import DeliveryRateState, EmailServiceConfig
from apps.core.services.delivery_rates import Family, active_target, channel_info
from apps.mail.admin.settings.rate_cards.lines import reported_lines
from apps.mail.admin.settings.rate_cards.placeholders import Channel

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
