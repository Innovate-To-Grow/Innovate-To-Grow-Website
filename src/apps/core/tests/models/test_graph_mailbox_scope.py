"""``MicrosoftGraphMailboxScope`` and the scope-aware readiness checks on ``MicrosoftGraphProviderConfig``."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.core.models import MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.models.base.service_credentials.microsoft_graph import normalize_mailbox
from apps.core.tests.graph_helpers import create_graph_config, grant

Permission = MicrosoftGraphMailboxScope.Permission
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SENDER = "i2g@contoso.com"


def active_config(**overrides):
    values = {
        "name": "Graph",
        "is_active": True,
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "client_secret": "not-a-real-secret",
    }
    return create_graph_config(**{**values, **overrides})


class MailboxScopeModelTests(TestCase):
    def setUp(self):
        self.config = active_config()

    def test_mailbox_is_stored_lowercase_and_trimmed(self):
        scope = MicrosoftGraphMailboxScope.objects.create(config=self.config, mailbox="  I2G@Contoso.COM ")

        scope.refresh_from_db()
        self.assertEqual(scope.mailbox, SENDER)
        self.assertEqual(scope.permission, Permission.SEND)

    def test_one_row_per_mailbox_and_config(self):
        grant(self.config, SENDER)

        with self.assertRaises(IntegrityError):
            MicrosoftGraphMailboxScope.objects.create(config=self.config, mailbox="I2G@contoso.com")

    def test_the_same_mailbox_may_appear_in_another_config(self):
        grant(self.config, SENDER)
        other = active_config(name="Standby", is_active=False)

        grant(other, SENDER)

        self.assertEqual(MicrosoftGraphMailboxScope.objects.filter(mailbox=SENDER).count(), 2)

    def test_grants_by_permission_level(self):
        expected = {
            Permission.SEND: {"send": True, "read": False},
            Permission.READ: {"send": False, "read": True},
            Permission.SEND_AND_READ: {"send": True, "read": True},
        }
        for level, grants in expected.items():
            scope = MicrosoftGraphMailboxScope(config=self.config, mailbox=SENDER, permission=level)
            for permission, allowed in {**grants, "delete": False, "": False}.items():
                with self.subTest(level=level, permission=permission):
                    self.assertIs(scope.grants(permission), allowed)

    def test_clean_normalizes_and_rejects_malformed_mailboxes(self):
        scope = MicrosoftGraphMailboxScope(config=self.config, mailbox=" Shared@Contoso.com ")
        scope.full_clean()
        self.assertEqual(scope.mailbox, "shared@contoso.com")

        guid = MicrosoftGraphMailboxScope(config=self.config, mailbox="72F988BF-86F1-41AF-91AB-2D7CD011DB47")
        guid.full_clean()

        for value in ("not a mailbox", "a@b.com\nBcc: x@y.com", "../users"):
            with self.subTest(value):
                with self.assertRaises(ValidationError) as caught:
                    MicrosoftGraphMailboxScope(config=self.config, mailbox=value).full_clean()
                self.assertIn("mailbox", caught.exception.message_dict)

    def test_str_shows_mailbox_and_permission(self):
        scope = MicrosoftGraphMailboxScope(config=self.config, mailbox=SENDER, permission=Permission.READ)

        self.assertEqual(str(scope), f"{SENDER} (Read only (Mail.Read))")

    def test_scope_rows_are_deleted_with_their_config(self):
        grant(self.config, SENDER)
        self.config.is_active = False
        self.config.save()

        self.config.delete()

        self.assertFalse(MicrosoftGraphMailboxScope.objects.exists())

    def test_rows_are_ordered_by_mailbox(self):
        grant(self.config, "zed@contoso.com", "amy@contoso.com")

        self.assertEqual(
            list(self.config.mailbox_scopes.values_list("mailbox", flat=True)), ["amy@contoso.com", "zed@contoso.com"]
        )

    def test_normalize_mailbox(self):
        self.assertEqual(normalize_mailbox(None), "")
        self.assertEqual(normalize_mailbox(" A@B.com "), "a@b.com")


class ConfigScopeTests(TestCase):
    def test_allows_is_case_insensitive_and_per_permission(self):
        config = active_config(scope=(SENDER,), permission=Permission.SEND)

        self.assertTrue(config.allows("I2G@Contoso.com", "send"))
        self.assertFalse(config.allows(SENDER, "read"))
        self.assertFalse(config.allows("other@contoso.com", "send"))
        self.assertFalse(config.allows("", "send"))

    def test_an_unsaved_config_allows_nothing(self):
        self.assertFalse(MicrosoftGraphProviderConfig(mailbox=SENDER).allows(SENDER, "send"))

    def test_is_configured_needs_at_least_one_scope_row(self):
        config = active_config()
        self.assertFalse(config.is_configured)

        grant(config, SENDER)

        self.assertTrue(config.is_configured)

    def test_is_configured_needs_an_active_saved_well_formed_config(self):
        self.assertFalse(MicrosoftGraphProviderConfig().is_configured)
        inactive = active_config(scope=(SENDER,), is_active=False)
        self.assertFalse(inactive.is_configured)

        config = active_config(scope=(SENDER,), name="Active")
        for field, value in {"mailbox": "not a mailbox", "client_secret": "", "tenant_id": "common"}.items():
            with self.subTest(field):
                MicrosoftGraphProviderConfig.objects.filter(pk=config.pk).update(**{field: value})
                config.refresh_from_db()
                self.assertFalse(config.is_configured)
                MicrosoftGraphProviderConfig.objects.filter(pk=config.pk).update(
                    mailbox="", client_secret="not-a-real-secret", tenant_id=TENANT_ID
                )

    def test_sender_mailbox_prefers_the_configured_mailbox(self):
        self.assertEqual(
            MicrosoftGraphProviderConfig(mailbox="Box@Contoso.com").sender_mailbox("x@y.com"), "box@contoso.com"
        )
        self.assertEqual(MicrosoftGraphProviderConfig().sender_mailbox(" From@Contoso.com"), "from@contoso.com")

    def test_sending_ready_when_the_from_address_is_the_sender(self):
        config = active_config(scope=(SENDER,), permission=Permission.SEND)

        self.assertTrue(config.sending_ready("I2G@contoso.com"))
        self.assertFalse(config.sending_ready("other@contoso.com"))

    def test_sending_ready_needs_send_on_both_mailbox_and_from(self):
        config = active_config(mailbox=SENDER, scope=(SENDER,), permission=Permission.SEND)
        self.assertFalse(config.sending_ready("alias@contoso.com"))

        grant(config, "alias@contoso.com", permission=Permission.READ)
        self.assertFalse(config.sending_ready("alias@contoso.com"))

        config.mailbox_scopes.filter(mailbox="alias@contoso.com").update(permission=Permission.SEND_AND_READ)
        self.assertTrue(config.sending_ready("alias@contoso.com"))

    def test_sending_ready_refuses_read_only_sender_and_unconfigured_configs(self):
        read_only = active_config(scope=(SENDER,), permission=Permission.READ)
        self.assertFalse(read_only.sending_ready(SENDER))

        self.assertFalse(MicrosoftGraphProviderConfig().sending_ready(SENDER))
