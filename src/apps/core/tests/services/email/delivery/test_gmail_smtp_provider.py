"""The ``gmail_smtp`` provider: an Inbox reply sent as one Gmail access account, over SMTP with its own login."""

from types import SimpleNamespace

from django.test import TestCase

from apps.core.models import GmailAccessAccount
from apps.core.services.email import PermanentEmailDeliveryError, SMTPProvider, resolve_provider


def reply_account(**overrides):
    values = {
        "name": "Replies",
        "is_active": False,
        "imap_host": "imap.gmail.com",
        "gmail_username": "reply@gmail.com",
        "gmail_password": "app-password",
        "reply_enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 2525,
    }
    return GmailAccessAccount.objects.create(**{**values, **overrides})


def stand_in(account_id, **overrides):
    """The configuration ``inbox.senders.SendIdentity.delivery_config`` builds for an IMAP sender."""
    values = {
        "provider": "gmail_smtp",
        "from_email": "reply@gmail.com",
        "from_name": "I2G",
        "is_active": True,
        "gmail_account_id": account_id,
    }
    return SimpleNamespace(**{**values, **overrides})


class GmailSmtpFactoryTests(TestCase):
    def test_builds_an_smtp_provider_with_the_account_login(self):
        provider = resolve_provider(stand_in(reply_account().pk))

        self.assertIsInstance(provider, SMTPProvider)
        self.assertEqual((provider.host, provider.port), ("smtp.example.com", 2525))
        self.assertEqual((provider.username, provider.password), ("reply@gmail.com", "app-password"))
        self.assertEqual((provider.from_email, provider.from_name), ("reply@gmail.com", "I2G"))
        self.assertTrue(provider.use_tls)
        self.assertFalse(provider.use_ssl)

    def test_sends_from_the_account_whatever_the_stand_in_names(self):
        provider = resolve_provider(stand_in(reply_account().pk, from_email="spoofed@example.com"))

        self.assertEqual(provider.from_email, "reply@gmail.com")

    def test_a_missing_from_name_is_blank(self):
        config = stand_in(reply_account().pk)
        del config.from_name

        self.assertEqual(resolve_provider(config).from_name, "")

    def test_refuses_once_replies_are_turned_off(self):
        with self.assertRaisesMessage(PermanentEmailDeliveryError, "not enabled"):
            resolve_provider(stand_in(reply_account(reply_enabled=False).pk))

    def test_refuses_without_a_login_or_smtp_server(self):
        for field, value in (("gmail_username", ""), ("gmail_password", ""), ("smtp_host", ""), ("smtp_port", 0)):
            with self.subTest(field), self.assertRaisesMessage(PermanentEmailDeliveryError, "not enabled"):
                resolve_provider(stand_in(reply_account(**{field: value}).pk))

    def test_refuses_a_missing_or_unnamed_account(self):
        deleted = reply_account()
        missing = deleted.pk
        deleted.delete()
        for config in (stand_in(missing), stand_in(None), SimpleNamespace(provider="gmail_smtp", from_name="")):
            with self.subTest(config=config), self.assertRaisesMessage(PermanentEmailDeliveryError, "not enabled"):
                resolve_provider(config)
