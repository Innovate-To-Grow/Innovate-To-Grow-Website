"""Delivery channels: their family, signal adapter and cooldown group, the lanes, and the identity formats.

A channel's policy (``DeliveryRatePolicy``) is shared by the whole channel; its pacing state (``DeliveryRateState``)
is kept per identity (a sender mailbox, an SES account and Region, an SMTP login, an SMS origination number, ...),
so a new identity starts with fresh state. Identities that share one provider allowance share a cooldown group.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from apps.core.models.base.delivery_rates import DeliveryChannel

# ``DeliveryRateState.identity`` and ``cooldown_group`` are 512-character columns.
MAX_IDENTITY_LENGTH = 512


class Lane(StrEnum):
    """Who is sending: login codes, tickets and replies (all of the rate and every daily limit), or campaigns."""

    TRANSACTIONAL = "transactional"
    BULK = "bulk"


class Family(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    INBOX = "inbox"


@dataclass(frozen=True)
class ChannelInfo:
    channel: str
    family: Family
    # Key of the channel's provider answers in DELIVERY_RATES["signals"].
    adapter: str
    # Builds the cooldown group from an identity.
    group: Callable[[str], str]
    # Who answers, for the status lines ("Microsoft Graph asked to wait 10 s").
    provider: str
    # True when the provider reports its limits at runtime (``runtime.discovery``).
    discovers: bool = False


def _after_first_colon(identity: str) -> str:
    return identity.split(":", 1)[-1]


def _before_first_colon(identity: str) -> str:
    return identity.split(":", 1)[0]


CHANNELS = {
    # Outlook "applies limits to each app ID and mailbox combination", which Graph sends and reads share.
    DeliveryChannel.GRAPH_SEND: ChannelInfo(
        DeliveryChannel.GRAPH_SEND, Family.EMAIL, "graph", lambda i: f"graph:{i}", "Microsoft Graph"
    ),
    DeliveryChannel.GRAPH_READ: ChannelInfo(
        DeliveryChannel.GRAPH_READ, Family.INBOX, "graph", lambda i: f"graph:{i}", "Microsoft Graph"
    ),
    # SES quotas are per account and Region (identity "<config>:<region>").
    DeliveryChannel.SES_SEND: ChannelInfo(
        DeliveryChannel.SES_SEND, Family.EMAIL, "ses", lambda i: f"ses:{_after_first_colon(i)}", "AWS", True
    ),
    DeliveryChannel.SMTP_SEND: ChannelInfo(
        DeliveryChannel.SMTP_SEND, Family.EMAIL, "smtp", lambda i: f"smtp:{i}", "The SMTP server"
    ),
    # Gmail limits are per Google account (identity "<imap host>:<username>").
    DeliveryChannel.GMAIL_IMAP: ChannelInfo(
        DeliveryChannel.GMAIL_IMAP, Family.INBOX, "imap", lambda i: f"gmail:{_after_first_colon(i)}", "Gmail"
    ),
    # Gmail API bandwidth limits are "equal to, but independent of, IMAP", so the group is not shared with IMAP.
    DeliveryChannel.GMAIL_API_SEND: ChannelInfo(
        DeliveryChannel.GMAIL_API_SEND, Family.EMAIL, "gmail_api", lambda i: f"gmail_api:{i}", "The Gmail API"
    ),
    # The SendTextMessage quota is per account and Region (identity "<region>:<origination>").
    DeliveryChannel.SMS_SEND: ChannelInfo(
        DeliveryChannel.SMS_SEND, Family.SMS, "sms", lambda i: f"sms:{_before_first_colon(i)}", "AWS SMS", True
    ),
}


def channel_info(channel: str) -> ChannelInfo:
    try:
        return CHANNELS[channel]
    except KeyError:
        raise ValueError(f"Unknown delivery channel: {channel!r}") from None


def cooldown_group(channel: str, identity: str) -> str:
    """The identity's cooldown group (both checked to fit their columns)."""
    return _checked(channel_info(channel).group(_checked(identity)))


def _checked(identity: str) -> str:
    if not identity or len(identity) > MAX_IDENTITY_LENGTH:
        raise ValueError(f"A delivery identity must have 1 to {MAX_IDENTITY_LENGTH} characters.")
    return identity


def mailbox_identity(mailbox: str) -> str:
    """Graph sender mailbox, or the Gmail API subject."""
    return _checked(str(mailbox).strip().lower())


def ses_identity(config_pk, region: str) -> str:
    return _checked(f"{config_pk}:{str(region).strip().lower()}")


def smtp_identity(host: str, port, username: str) -> str:
    return _checked(f"{str(host).strip()}:{port}:{str(username).strip()}".lower())


def imap_identity(host: str, username: str) -> str:
    return _checked(f"{str(host).strip()}:{str(username).strip()}".lower())


def sms_identity(region: str, origination: str) -> str:
    return _checked(f"{str(region).strip().lower()}:{str(origination).strip()}")


def smtp_host(identity: str) -> str:
    return _before_first_colon(identity)


def external_recipients(addresses: Iterable[str], internal_domain: str, *, subdomains: bool) -> int:
    """How many ``addresses`` are outside ``internal_domain`` (all of them when it is blank).

    Graph counts the sender's domain and its subdomains as internal (``subdomains=True``); Google counts only the
    Workspace primary domain.
    """
    domain = str(internal_domain or "").strip().lower()
    count = 0
    for address in addresses:
        host = str(address).rpartition("@")[2].strip().lower()
        internal = bool(domain) and (host == domain or (subdomains and host.endswith(f".{domain}")))
        count += not internal
    return count
