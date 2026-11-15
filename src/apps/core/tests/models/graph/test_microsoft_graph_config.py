"""MicrosoftGraphProviderConfig and the Microsoft Graph branches of EmailServiceConfig."""

import uuid

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from apps.core.models import (
    MicrosoftGraphProviderConfig,
)
from apps.core.tests.graph_helpers import create_graph_config, grant, install_test_certificate

TENANT_ID = "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OBJECT_ID = "99999999-8888-7777-6666-555555555555"
MAILBOX = "sender@example.com"
# Every sender these tests use is in scope; the scope rules have their own tests.
SCOPE = (MAILBOX, "shared@example.com", "noreply@example.com", OBJECT_ID)


def graph_fields(**overrides):
    """Field values for a complete, valid Graph configuration."""
    fields = {
        "name": "Mail",
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "mailbox": MAILBOX,
    }
    return fields | overrides


def make_graph(**overrides):
    """Persist a Graph configuration through save(), so it passes the validation the admin applies."""
    return create_graph_config(scope=SCOPE, **graph_fields(**overrides))


def store_graph_unvalidated(certificate=True, **overrides):
    """Replace every Graph row with one written without save() or validation, as a script could.

    *certificate* installs a current certificate (``True``, or a dict of ``install_test_certificate`` options).
    """
    MicrosoftGraphProviderConfig.objects.all().delete()
    row = MicrosoftGraphProviderConfig.objects.bulk_create([MicrosoftGraphProviderConfig(**graph_fields(**overrides))])[
        0
    ]
    if certificate:
        install_test_certificate(row, **(certificate if isinstance(certificate, dict) else {}))
    return grant(row, *SCOPE)


def loaded(**overrides):
    """An active stored configuration (with its mailbox scope) written without validation, as a script could."""
    return store_graph_unvalidated(**{"is_active": True, **overrides})


class GraphConfigDefaultsTest(SimpleTestCase):
    def test_new_config_is_inactive_without_a_certificate_or_mailbox(self):
        config = MicrosoftGraphProviderConfig()

        self.assertIsNone(config.current_certificate)
        self.assertIsNone(config.certificate_expires_at)
        self.assertEqual(config.mailbox, "")
        self.assertFalse(config.is_active)
        self.assertFalse(config.is_configured)

    def test_primary_key_is_a_uuid(self):
        self.assertIsInstance(MicrosoftGraphProviderConfig().pk, uuid.UUID)


class GraphConfigStrTest(SimpleTestCase):
    def test_shows_the_name_and_mailbox_of_an_active_config(self):
        config = MicrosoftGraphProviderConfig(**graph_fields(is_active=True))

        self.assertEqual(str(config), f"Mail: {MAILBOX} (active)")

    def test_falls_back_to_the_client_id_without_a_mailbox(self):
        config = MicrosoftGraphProviderConfig(**graph_fields(mailbox=""))

        self.assertEqual(str(config), f"Mail: {CLIENT_ID}")

    def test_reports_not_configured_when_nothing_identifies_the_app(self):
        self.assertEqual(str(MicrosoftGraphProviderConfig(name="Blank")), "Blank: not configured")


class GraphConfigCleanTest(TestCase):
    # clean() of an active config asks whether email is sent through Graph, so these tests need the database.

    def errors(self, **overrides):
        """Field errors clean() raises for an otherwise valid config, or {} when it passes."""
        try:
            MicrosoftGraphProviderConfig(**graph_fields(**overrides)).clean()
        except ValidationError as error:
            return error.message_dict
        return {}

    def field_errors(self, **overrides):
        """Field errors from full_clean(), restricted to field validators and clean() (no unique checks)."""
        try:
            config = MicrosoftGraphProviderConfig(**graph_fields(**overrides))
            config.full_clean(validate_unique=False, validate_constraints=False)
        except ValidationError as error:
            return error.message_dict
        return {}

    def test_complete_configuration_is_valid(self):
        self.assertEqual(self.errors(), {})

    def test_tenant_accepts_a_guid_or_a_verified_domain(self):
        for tenant in (TENANT_ID, TENANT_ID.upper(), "contoso.onmicrosoft.com", "mail.contoso.com"):
            with self.subTest(tenant=tenant):
                self.assertEqual(self.errors(tenant_id=tenant), {})

    def test_tenant_rejects_aliases_and_anything_that_is_not_one_path_segment(self):
        rejected = (
            "common",
            "organizations",
            "consumers",
            "a/b",
            "contoso.com/oauth2",
            "contoso.com?x=1",
            "con toso.com",
            "https://contoso.com",
        )
        for tenant in rejected:
            with self.subTest(tenant=tenant):
                self.assertEqual(list(self.errors(tenant_id=tenant)), ["tenant_id"])

    def test_client_id_must_be_a_guid(self):
        self.assertEqual(self.errors(client_id=CLIENT_ID.upper()), {})
        for client_id in ("my-app", CLIENT_ID.replace("-", ""), f"{{{CLIENT_ID}}}", CLIENT_ID + "0"):
            with self.subTest(client_id=client_id):
                self.assertEqual(list(self.errors(client_id=client_id)), ["client_id"])

    def test_mailbox_accepts_an_address_an_object_id_or_nothing(self):
        for mailbox in ("", MAILBOX, "first.last@school.contoso.onmicrosoft.com", OBJECT_ID):
            with self.subTest(mailbox=mailbox):
                self.assertEqual(self.errors(mailbox=mailbox), {})

    def test_mailbox_rejects_values_that_are_neither_an_address_nor_a_guid(self):
        for mailbox in ("not a mailbox", "sender@", "@example.com", "sender@@example.com", "sender"):
            with self.subTest(mailbox=mailbox):
                self.assertEqual(list(self.errors(mailbox=mailbox)), ["mailbox"])

    def test_a_config_may_be_saved_before_its_certificate_is_installed(self):
        # The certificate is installed on a saved config; until then the config is simply not configured.
        self.assertEqual(self.errors(is_active=True), {})

    def test_every_invalid_field_is_reported_at_once(self):
        errors = self.errors(is_active=True, tenant_id="common", client_id="x", mailbox="x")

        self.assertEqual(sorted(errors), ["client_id", "mailbox", "tenant_id"])

    def test_tenant_and_client_id_are_required_fields(self):
        for field in ("tenant_id", "client_id"):
            with self.subTest(field=field):
                self.assertEqual(list(self.field_errors(**{field: ""})), [field])
