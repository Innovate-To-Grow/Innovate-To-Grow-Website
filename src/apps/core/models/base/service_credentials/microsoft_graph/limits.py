"""Sending limits of a Graph configuration: their defaults (the DELIVERY_RATES seeds of the Graph send channel) and
the fields that hold them. Migration 0043 names the defaults through the package, which re-exports them."""

from django.conf import settings


# The sending-limit fields start from the DELIVERY_RATES seeds of the Graph send channel (documented Exchange Online
# limits, with their sources); once a configuration is active, the values entered on it are what the channel uses.
def _graph_seed(key: str):
    return settings.DELIVERY_RATES["channels"]["graph_send"][key]


def default_max_recipients_per_message() -> int:
    return _graph_seed("max_recipients_per_message")


def default_messages_per_minute_limit() -> int:
    return _graph_seed("provider_limit")


def default_recipients_per_day_limit() -> int:
    return _graph_seed("daily_limit")


def default_external_recipients_per_hour_limit():
    return _graph_seed("hourly_external_limit")


def default_internal_recipients_per_hour_limit():
    return _graph_seed("hourly_internal_limit")


SENDING_LIMIT_FIELDS = (
    "max_recipients_per_message",
    "messages_per_minute_limit",
    "recipients_per_day_limit",
    "external_recipients_per_hour_limit",
    "internal_recipients_per_hour_limit",
)
_LIMITS_WHERE = "Mail → Delivery Rates (Email · Microsoft Graph)"
