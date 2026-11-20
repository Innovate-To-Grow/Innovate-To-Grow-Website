"""Fixtures for the inbox service-layer tests: a saved Gmail account, fake IMAP messages, and an inbox context."""

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

from apps.core.models import GmailAccessAccount


@contextmanager
def _inbox_context(client):
    yield client


def create_gmail_account(**overrides):
    """A configured Gmail IMAP access account: the inbox reads only accounts saved in the database."""
    values = {
        "name": "Gmail",
        "is_active": True,
        "imap_host": "imap.gmail.com",
        "gmail_username": "i2g@gmail.com",
        "gmail_password": "app-password",
    }
    return GmailAccessAccount.objects.create(**{**values, **overrides})


def _fake_message(**overrides):
    defaults = {
        "uid": "42",
        "subject": "Hi there",
        "from_values": SimpleNamespace(name="Alice", email="alice@example.com"),
        "from_": "alice@example.com",
        "to_values": [SimpleNamespace(name="Bob", email="bob@example.com")],
        "date": datetime(2026, 1, 1, 9, 30),
        "html": "<p>Hello <b>world</b></p>",
        "text": "Hello world",
        "flags": ("\\Seen",),
        "headers": {"message-id": ["<m@example.com>"], "references": ["<r@example.com>"]},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)
