"""Default ceilings for one Gmail API message (recipients, size), from the GMAIL_API settings. Migration 0038 names
them through the package, which re-exports them."""

from django.conf import settings


def default_max_recipients() -> int:
    return settings.GMAIL_API["max_recipients_per_message"]


def default_max_message_bytes() -> int:
    return settings.GMAIL_API["max_message_bytes"]
