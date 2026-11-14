"""The delivery channels, and the unit each one's stored rates are in."""

from typing import NamedTuple

from django.db import models


class RateUnit(NamedTuple):
    """What a channel's rates count and per how many seconds, and what its daily budget counts."""

    label: str
    per_seconds: int
    budget: str = "recipients"


class DeliveryChannel(models.TextChoices):
    GRAPH_SEND = "graph_send", "Email · Microsoft Graph"
    GRAPH_READ = "graph_read", "Inbox · Microsoft Graph"
    SES_SEND = "ses_send", "Email · Amazon SES"
    SMTP_SEND = "smtp_send", "Email · SMTP"
    GMAIL_IMAP = "gmail_imap", "Inbox · Gmail"
    GMAIL_API_SEND = "gmail_api_send", "Email · Gmail API"
    SMS_SEND = "sms_send", "SMS · AWS End User Messaging"


# The unit each channel's stored rates are in. Changing one would reinterpret every stored value, so it is part of
# the schema rather than a setting.
CHANNEL_UNITS = {
    DeliveryChannel.GRAPH_SEND: RateUnit("messages/min", 60),
    DeliveryChannel.GRAPH_READ: RateUnit("requests/min", 60, budget=""),
    DeliveryChannel.SES_SEND: RateUnit("recipients/sec", 1),
    DeliveryChannel.SMTP_SEND: RateUnit("messages/min", 60),
    DeliveryChannel.GMAIL_IMAP: RateUnit("sessions/min", 60, budget=""),
    DeliveryChannel.GMAIL_API_SEND: RateUnit("messages/min", 60),
    DeliveryChannel.SMS_SEND: RateUnit("messages/sec", 1, budget="messages"),
}
