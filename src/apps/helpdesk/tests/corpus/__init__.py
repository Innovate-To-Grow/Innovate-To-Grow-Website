"""Synthetic inbound mail for the helpdesk tests, built in the shapes real systems send (the repo is public: no real
person's mail). Each builder returns raw RFC 5322 bytes, as Microsoft Graph's ``$value`` would."""

from .automated import (
    bounce_report,
    calendar_reply,
    esp_newsletter,
    german_auto_reply,
    gmail_vacation,
    left_organisation,
    list_mail,
    out_of_office,
    read_receipt,
    spam,
)
from .base import (
    CRLF,
    IMPERSONATE_LINK,
    LOGIN_LINK,
    SITE,
    UNSUBSCRIBE_LINK,
    _join,
    message,
)
from .people import (
    forwarded,
    own_message,
)

__all__ = [
    "_join",
    "bounce_report",
    "calendar_reply",
    "CRLF",
    "esp_newsletter",
    "forwarded",
    "german_auto_reply",
    "gmail_vacation",
    "IMPERSONATE_LINK",
    "left_organisation",
    "list_mail",
    "LOGIN_LINK",
    "message",
    "out_of_office",
    "own_message",
    "read_receipt",
    "SITE",
    "spam",
    "UNSUBSCRIBE_LINK",
]
