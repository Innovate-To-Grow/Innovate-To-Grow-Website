"""``inbox.senders``: resolving a sender key, picking the default sender for a message, and its delivery config."""

from types import SimpleNamespace

from django.test import TestCase

from apps.mail.services.inbox.sending.senders import (
    DEFAULT_SENDER,
    SendIdentity,
    default_identity_for,
    resolve_identity,
)
from apps.mail.tests.services.delivery.graph_inbox.helpers import MAILBOX, graph_config
from apps.mail.tests.services.inbox.senders.helpers import (
    DEFAULT_ADDRESS,
    SenderFixtureMixin,
)


class ResolveIdentityTests(SenderFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.default_sender()
        graph_config()

    def test_no_key_is_the_default(self):
        for key in (None, "", DEFAULT_SENDER):
            with self.subTest(key=key):
                self.assertEqual(resolve_identity(key).key, DEFAULT_SENDER)

    def test_a_listed_key(self):
        self.assertEqual(resolve_identity(f"graph:{MAILBOX}").address, MAILBOX)

    def test_an_unlisted_key_is_none(self):
        for key in ("graph:other@contoso.com", "imap:999999", "gmail_api:x@example.com", "bogus"):
            with self.subTest(key=key):
                self.assertIsNone(resolve_identity(key))


class DefaultIdentityForTests(TestCase):
    identities = [
        SendIdentity(DEFAULT_SENDER, DEFAULT_ADDRESS, "ses", "Notification Delivery"),
        SendIdentity("imap:1", "Reply@Gmail.com", "gmail_smtp", "SMTP", 1),
    ]

    def test_the_address_the_message_was_received_at(self):
        self.assertEqual(default_identity_for(self.identities, " reply@gmail.com ").key, "imap:1")

    def test_else_the_first_choice(self):
        for address in ("someone@else.com", "", None):
            with self.subTest(address=address):
                self.assertEqual(default_identity_for(self.identities, address).key, DEFAULT_SENDER)

    def test_no_choice_is_none(self):
        self.assertIsNone(default_identity_for([], DEFAULT_ADDRESS))


class DeliveryConfigTests(TestCase):
    base = SimpleNamespace(provider="ses", from_email=DEFAULT_ADDRESS, from_name="I2G", is_active=True)

    def test_the_default_sends_with_notification_delivery_itself(self):
        identity = SendIdentity(DEFAULT_SENDER, DEFAULT_ADDRESS, "ses", "Notification Delivery")

        self.assertIs(identity.delivery_config(self.base), self.base)

    def test_another_sender_gets_a_stand_in_naming_its_provider_and_address(self):
        identity = SendIdentity("imap:7", "reply@gmail.com", "gmail_smtp", "SMTP", 7)

        config = identity.delivery_config(self.base)

        self.assertEqual(
            vars(config),
            {
                "provider": "gmail_smtp",
                "from_email": "reply@gmail.com",
                "from_name": "I2G",
                "is_active": True,
                "gmail_account_id": 7,
            },
        )
