"""``inbox.senders``: the From addresses an Inbox reply may use, each gated by its provider's own readiness."""

from types import SimpleNamespace
from unittest.mock import patch

from django.db.utils import OperationalError
from django.test import TestCase

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GmailAccessAccount,
    GmailApiProviderConfig,
    GmailApiSubject,
    MicrosoftGraphCertificate,
    MicrosoftGraphProviderConfig,
)
from apps.core.tests.gmail_api_helpers import make_config
from apps.core.tests.graph_helpers import grant
from apps.mail.services.inbox.senders import (
    DEFAULT_SENDER,
    SendIdentity,
    default_identity_for,
    resolve_identity,
    send_identities,
)
from apps.mail.tests.services.delivery.graph_inbox.test_graph_inbox_backend import MAILBOX, Permission, graph_config
from apps.mail.tests.services.inbox.accounts.helpers import gmail_account

DEFAULT_ADDRESS = "notify@ucmerced.edu"
WORKSPACE = "i2g@g.ucmerced.edu"


class SenderFixtureMixin:
    def setUp(self):
        super().setUp()
        for model in (EmailServiceConfig, MicrosoftGraphProviderConfig, GmailApiProviderConfig, GmailAccessAccount):
            model.objects.all().delete()

    def default_sender(self, from_email=DEFAULT_ADDRESS):
        """Notification Delivery on SES, which is ready once AWS credentials are active."""
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        return EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="ses", from_email=from_email, from_name="I2G"
        )

    def reply_account(self, username="reply@gmail.com", **overrides):
        return gmail_account(username, **{"is_active": False, "reply_enabled": True, **overrides})


class SendIdentitiesTests(SenderFixtureMixin, TestCase):
    def keys(self):
        return [identity.key for identity in send_identities()]

    def test_nothing_configured_offers_nothing(self):
        self.assertEqual(send_identities(), [])

    def test_every_source_in_order(self):
        self.default_sender()
        graph_config()
        make_config(subjects=(WORKSPACE,))
        row = self.reply_account()

        identities = send_identities()

        self.assertEqual(
            [identity.key for identity in identities],
            [DEFAULT_SENDER, f"graph:{MAILBOX}", f"gmail_api:{WORKSPACE}", f"imap:{row.pk}"],
        )
        self.assertEqual(
            [(identity.address, identity.provider) for identity in identities],
            [(DEFAULT_ADDRESS, "ses"), (MAILBOX, "graph"), (WORKSPACE, "gmail"), ("reply@gmail.com", "gmail_smtp")],
        )
        self.assertEqual(identities[0].via, "Notification Delivery · AWS SES")
        self.assertEqual(identities[3].label, "reply@gmail.com (SMTP · smtp.gmail.com)")
        self.assertEqual(identities[3].gmail_account_id, row.pk)

    def test_the_default_is_left_out_until_delivery_is_configured(self):
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email=DEFAULT_ADDRESS)

        self.assertEqual(self.keys(), [])

    def test_an_inactive_default_is_left_out(self):
        self.default_sender()
        EmailServiceConfig.objects.update(is_active=False)

        self.assertEqual(self.keys(), [])

    def test_graph_send_scopes_only(self):
        config = graph_config()
        grant(config, "reader@contoso.com", permission=Permission.READ)
        grant(config, "Not An Address", permission=Permission.SEND)

        self.assertEqual(self.keys(), [f"graph:{MAILBOX}"])

    def test_graph_is_left_out_while_it_has_a_takeover_problem(self):
        graph_config()
        MicrosoftGraphCertificate.objects.update(entra_check=MicrosoftGraphCertificate.EntraCheck.NOT_TRUSTED)

        self.assertEqual(self.keys(), [])

    def test_graph_is_left_out_when_not_configured(self):
        graph_config(is_active=False)

        self.assertEqual(self.keys(), [])

    def test_gmail_api_subjects_only_once_verified(self):
        make_config(subjects=(WORKSPACE, "other@g.ucmerced.edu"))
        GmailApiSubject.objects.filter(subject="other@g.ucmerced.edu").update(verified_at=None)

        self.assertEqual(self.keys(), [f"gmail_api:{WORKSPACE}"])

    def test_gmail_api_is_left_out_when_not_configured(self):
        make_config(subjects=(WORKSPACE,), active=False)

        self.assertEqual(self.keys(), [])

    def test_imap_accounts_only_with_replies_enabled_and_a_login(self):
        allowed = self.reply_account("allowed@gmail.com")
        self.reply_account("nopass@gmail.com", gmail_password="")
        self.reply_account("nohost@gmail.com", smtp_host="")
        gmail_account("disabled@gmail.com", is_active=False, reply_enabled=False)
        self.reply_account("not an address")

        self.assertEqual(self.keys(), [f"imap:{allowed.pk}"])

    def test_the_active_imap_account_leads(self):
        other = self.reply_account("aa@gmail.com")
        active = self.reply_account("zz@gmail.com", is_active=True)

        self.assertEqual(self.keys(), [f"imap:{active.pk}", f"imap:{other.pk}"])

    def test_an_address_offered_twice_keeps_the_earlier_source(self):
        self.default_sender(from_email=MAILBOX)
        graph_config()
        self.reply_account(MAILBOX.upper())

        identities = send_identities()

        self.assertEqual([(identity.key, identity.provider) for identity in identities], [(DEFAULT_SENDER, "ses")])

    def test_one_broken_source_does_not_hide_the_others(self):
        row = self.reply_account()

        with (
            patch("apps.mail.services.inbox.senders.GmailApiProviderConfig.load", side_effect=RuntimeError("boom")),
            self.assertLogs("apps.mail.services.inbox.senders", "ERROR"),
        ):
            self.assertEqual(self.keys(), [f"imap:{row.pk}"])

    def test_missing_tables_are_raised(self):
        with (
            patch("apps.mail.services.inbox.senders.EmailServiceConfig.load", side_effect=OperationalError("no table")),
            self.assertRaises(OperationalError),
        ):
            send_identities()


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
