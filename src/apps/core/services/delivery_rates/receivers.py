"""Saving a delivery configuration half-opens its channels' auth and permission breakers: the next request probes
at once instead of waiting for the timed probe, because the save is usually the fix (new credentials, a granted
mailbox, another sender).

``connect`` runs from ``CoreConfig.ready``. A configuration model added later registers its channels with
``register_config_channels`` before ``connect`` runs (or connects itself by calling it again).
"""

from functools import partial

from django.apps import apps
from django.db import transaction
from django.db.models.signals import post_save

from apps.core.models.base.delivery_rates import DeliveryChannel

from .runtime import context
from .runtime.breaker import config_stopped, half_open_for_config

_EMAIL_SENDERS = (
    DeliveryChannel.GRAPH_SEND,
    DeliveryChannel.SES_SEND,
    DeliveryChannel.SMTP_SEND,
    DeliveryChannel.GMAIL_API_SEND,
)
_GRAPH = (DeliveryChannel.GRAPH_SEND, DeliveryChannel.GRAPH_READ)
CONFIG_CHANNELS: dict[str, tuple[str, ...]] = {
    # The From address and the provider choice decide what every email sender may send as.
    "core.EmailServiceConfig": _EMAIL_SENDERS,
    "core.AWSCredentialConfig": (DeliveryChannel.SES_SEND, DeliveryChannel.SMS_SEND),
    "core.SMTPProviderConfig": (DeliveryChannel.SMTP_SEND,),
    "core.MicrosoftGraphProviderConfig": _GRAPH,
    "core.MicrosoftGraphCertificate": _GRAPH,
    "core.MicrosoftGraphMailboxScope": _GRAPH,
    "core.GmailAccessAccount": (DeliveryChannel.GMAIL_IMAP,),
}


def register_config_channels(model_label: str, channels) -> None:
    CONFIG_CHANNELS[model_label] = tuple(channels)


def half_open_after_commit(channels) -> None:
    half_open_for_config(channels, context.clock())


def _saved(sender, instance, raw=False, **kwargs):
    if raw:
        return  # fixture loading
    channels = CONFIG_CHANNELS.get(sender._meta.label)
    # Only a save that may fix a stopped identity leaves work for after the commit (most saves find none).
    if channels and config_stopped(channels).exists():
        transaction.on_commit(partial(half_open_after_commit, channels), robust=True)


def connect() -> None:
    for label in CONFIG_CHANNELS:
        post_save.connect(_saved, sender=apps.get_model(label), dispatch_uid=f"delivery_rates_config_saved:{label}")
