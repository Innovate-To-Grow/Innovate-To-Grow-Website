"""Limits the operator entered on a provider's configuration: the tenant's own numbers, which replace the documented
ceilings of ``DELIVERY_RATES`` for that channel.

Microsoft Graph: the sender mailbox's limits as OIT states them live on the active ``MicrosoftGraphProviderConfig``
(``max_recipients_per_message``, ``messages_per_minute_limit``, ``recipients_per_day_limit`` and the two hourly
recipient limits; the Core app's admin page). ``DELIVERY_RATES["channels"]["graph_send"]`` seeds those fields and
applies only while no active Graph configuration exists.
"""

from django.db import DatabaseError

from apps.core.models.base.delivery_rates import (
    LIMITS_SOURCE_KEY,
    TENANT_LIMITS,
    DeliveryChannel,
    limits_from_configuration,
)

# Spec key → MicrosoftGraphProviderConfig field.
GRAPH_LIMIT_FIELDS = {
    "provider_limit": "messages_per_minute_limit",
    "daily_limit": "recipients_per_day_limit",
    "hourly_external_limit": "external_recipients_per_hour_limit",
    "hourly_internal_limit": "internal_recipients_per_hour_limit",
    "max_recipients_per_message": "max_recipients_per_message",
}


def configured_limits(channel: str) -> dict:
    """The spec keys *channel*'s active provider configuration overrides, or ``{}`` (no such configuration, another
    channel, or a database that cannot be read, as during a migration)."""
    if channel != DeliveryChannel.GRAPH_SEND:
        return {}
    from apps.core.models import MicrosoftGraphProviderConfig

    try:
        row = MicrosoftGraphProviderConfig.objects.filter(is_active=True).values(*GRAPH_LIMIT_FIELDS.values()).first()
    except DatabaseError:
        return {}
    if row is None:
        return {}
    limits = {key: row[field] for key, field in GRAPH_LIMIT_FIELDS.items()}
    limits[LIMITS_SOURCE_KEY] = TENANT_LIMITS
    return limits


def from_tenant(spec: dict) -> bool:
    """Whether *spec*'s ceilings are the ones entered on the provider configuration."""
    return limits_from_configuration(spec)
