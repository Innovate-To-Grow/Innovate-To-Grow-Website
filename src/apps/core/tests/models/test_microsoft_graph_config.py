"""MicrosoftGraphProviderConfig and the Microsoft Graph branches of EmailServiceConfig."""

import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    MicrosoftGraphProviderConfig,
    SMTPProviderConfig,
)
from apps.core.tests.graph_helpers import create_graph_config, grant, install_test_certificate, private_key_lines

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


class GraphConfigSaveTest(TestCase):
    def test_save_rejects_a_blank_tenant_and_writes_nothing(self):
        config = MicrosoftGraphProviderConfig(**graph_fields(tenant_id=""))

        with self.assertRaises(ValidationError) as error:
            config.save()

        self.assertIn("tenant_id", error.exception.message_dict)
        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())

    def test_save_rejects_each_invalid_value_and_writes_nothing(self):
        invalid = (
            {"tenant_id": "common"},
            {"client_id": "not-a-guid"},
            {"mailbox": "garbage"},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                MicrosoftGraphProviderConfig(**graph_fields(**overrides)).save()

        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())

    def test_activating_a_second_config_deactivates_the_first(self):
        first = make_graph(name="First", is_active=True)
        second = make_graph(name="Second", is_active=True)

        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(MicrosoftGraphProviderConfig.load(), second)
        self.assertEqual(MicrosoftGraphProviderConfig.objects.filter(is_active=True).count(), 1)

    def test_rejected_activation_leaves_the_current_active_config_in_place(self):
        current = make_graph(name="Current", is_active=True)

        with self.assertRaises(ValidationError):
            MicrosoftGraphProviderConfig(**graph_fields(name="Next", is_active=True, tenant_id="common")).save()

        current.refresh_from_db()
        self.assertTrue(current.is_active)
        self.assertEqual(MicrosoftGraphProviderConfig.objects.count(), 1)

    def test_resaving_the_active_config_keeps_it_active(self):
        active = make_graph(is_active=True)

        active.name = "Renamed"
        active.save()

        active.refresh_from_db()
        self.assertTrue(active.is_active)
        self.assertEqual(active.name, "Renamed")

    def test_saving_an_inactive_config_leaves_the_active_one_alone(self):
        active = make_graph(name="Active", is_active=True)

        make_graph(name="Standby", certificate=False)

        active.refresh_from_db()
        self.assertTrue(active.is_active)

    def test_validation_does_not_reject_switching_the_active_config(self):
        make_graph(name="Active", is_active=True)
        standby = make_graph(name="Standby")
        standby.is_active = True

        standby.full_clean()

        self.assertEqual(MicrosoftGraphProviderConfig.objects.filter(is_active=True).count(), 1)

    def test_database_rejects_two_active_configs_when_save_is_bypassed(self):
        make_graph(name="Primary", is_active=True)
        standby = make_graph(name="Standby")

        with self.assertRaises(IntegrityError), transaction.atomic():
            MicrosoftGraphProviderConfig.objects.filter(pk=standby.pk).update(is_active=True)

        self.assertEqual(MicrosoftGraphProviderConfig.objects.filter(is_active=True).count(), 1)

    def test_single_active_constraint_has_the_documented_name(self):
        names = {constraint.name for constraint in MicrosoftGraphProviderConfig._meta.constraints}

        self.assertIn("core_one_active_graph_provider_config", names)


class GraphConfigLoadTest(TestCase):
    def test_returns_the_active_config(self):
        make_graph(name="Standby")
        active = make_graph(name="Active", is_active=True)

        self.assertEqual(MicrosoftGraphProviderConfig.load(), active)

    def test_returns_an_unsaved_default_when_nothing_is_active(self):
        config = MicrosoftGraphProviderConfig.load()

        self.assertTrue(config._state.adding)
        self.assertFalse(config.is_configured)
        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())

    def test_never_falls_back_to_an_inactive_config(self):
        inactive = make_graph(name="Inactive")

        config = MicrosoftGraphProviderConfig.load()

        self.assertTrue(config._state.adding)
        self.assertNotEqual(config.pk, inactive.pk)
        self.assertEqual((config.tenant_id, config.client_id), ("", ""))
        self.assertIsNone(config.current_certificate)
        self.assertFalse(config.is_configured)
        self.assertEqual(MicrosoftGraphProviderConfig.objects.count(), 1)


class GraphConfigIsConfiguredTest(TestCase):
    def test_requires_an_active_saved_config_with_every_credential(self):
        cases = (
            ("every credential present", {}, True),
            ("blank mailbox falls back to the From address", {"mailbox": ""}, True),
            ("inactive", {"is_active": False}, False),
            ("missing tenant", {"tenant_id": ""}, False),
            ("missing client id", {"client_id": ""}, False),
            ("no installed certificate", {"certificate": False}, False),
            ("expired certificate", {"certificate": {"days_valid": -1, "not_before_days": -30}}, False),
            ("certificate not valid yet", {"certificate": {"not_before_days": 2}}, False),
            ("previous certificate only", {"certificate": {"state": "previous"}}, False),
            ("tenant that is neither a GUID nor a domain", {"tenant_id": "common"}, False),
            ("tenant that adds a path segment", {"tenant_id": "contoso.com/../x"}, False),
            ("client id that is not a GUID", {"client_id": "not-a-guid"}, False),
            ("mailbox that is not an address or GUID", {"mailbox": "not a mailbox"}, False),
            ("object id mailbox", {"mailbox": OBJECT_ID}, True),
            ("domain tenant", {"tenant_id": "contoso.onmicrosoft.com"}, True),
        )
        for label, overrides, expected in cases:
            with self.subTest(label):
                self.assertIs(loaded(**overrides).is_configured, expected)

    def test_a_never_saved_instance_is_not_configured(self):
        config = MicrosoftGraphProviderConfig(**graph_fields(is_active=True))

        self.assertFalse(config.is_configured)


class GraphConfigSavedIsConfiguredTest(TestCase):
    def test_a_saved_active_config_is_configured(self):
        config = make_graph(is_active=True)

        self.assertTrue(config.is_configured)
        self.assertTrue(MicrosoftGraphProviderConfig.load().is_configured)

    def test_a_saved_inactive_config_is_not_configured(self):
        self.assertFalse(make_graph().is_configured)


class GraphConfigProposedScopeTest(TestCase):
    """``sending_ready(..., scopes=...)`` judges a scope that is not saved yet (the admin's guard), not the stored one."""

    def test_a_proposed_scope_replaces_the_stored_one(self):
        config = make_graph(is_active=True)
        cases = (
            ("the stored scope", None, True),
            ("an empty scope", {}, False),
            ("the sender with send rights", {MAILBOX: "send"}, True),
            ("the sender with read rights only", {MAILBOX: "read"}, False),
            ("another mailbox only", {"shared@example.com": "send_read"}, False),
        )
        for label, scopes, expected in cases:
            with self.subTest(label):
                self.assertIs(config.sending_ready(MAILBOX, scopes=scopes), expected)

    def test_a_proposed_scope_does_not_make_an_unsaved_or_inactive_config_ready(self):
        unsaved = MicrosoftGraphProviderConfig(**graph_fields(is_active=True))
        inactive = make_graph()

        for config in (unsaved, inactive):
            with self.subTest(saved=not config._state.adding):
                self.assertFalse(config.sending_ready(MAILBOX, scopes={MAILBOX: "send"}))


class EmailServiceConfigGraphProviderTest(SimpleTestCase):
    def test_graph_choice_has_the_documented_value_and_label(self):
        provider = EmailServiceConfig.Provider.GRAPH

        self.assertEqual(provider.value, "graph")
        self.assertEqual(provider.label, "Microsoft Graph")
        self.assertIn(("graph", "Microsoft Graph"), EmailServiceConfig.Provider.choices)
        self.assertEqual(EmailServiceConfig(provider="graph").get_provider_display(), "Microsoft Graph")

    def test_provider_field_offers_graph_and_every_value_fits(self):
        field = EmailServiceConfig._meta.get_field("provider")

        self.assertEqual(dict(field.choices)["graph"], "Microsoft Graph")
        for value in EmailServiceConfig.Provider.values:
            with self.subTest(value=value):
                self.assertLessEqual(len(value), field.max_length)


class EmailServiceConfigGraphActivationTest(TestCase):
    def pending(self, provider="graph"):
        return EmailServiceConfig(name="Pending", is_active=True, provider=provider, from_email=MAILBOX)

    def test_graph_activation_requires_a_configured_graph_config(self):
        with self.assertRaises(ValidationError) as error:
            self.pending().validate_activation()

        self.assertEqual(list(error.exception.message_dict), ["provider"])
        self.assertIn("Microsoft Graph", error.exception.message_dict["provider"][0])

    def test_graph_activation_ignores_inactive_and_incomplete_rows(self):
        rows = (("inactive row", {}), ("active row without a certificate", {"is_active": True, "certificate": False}))
        for label, overrides in rows:
            store_graph_unvalidated(**overrides)
            with self.subTest(label), self.assertRaises(ValidationError):
                self.pending().validate_activation()

    def test_graph_activation_passes_with_a_configured_graph_config(self):
        make_graph(is_active=True)

        self.pending().validate_activation()

    def test_inactive_email_config_is_not_validated(self):
        EmailServiceConfig(provider="graph", is_active=False).validate_activation()

    def test_ses_activation_still_requires_active_aws_credentials(self):
        make_graph(is_active=True)
        with self.assertRaises(ValidationError) as error:
            self.pending("ses").validate_activation()
        self.assertEqual(list(error.exception.message_dict), ["provider"])

        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="not-a-real-key", secret_access_key="not-a-real-aws-secret"
        )
        self.pending("ses").validate_activation()

    def test_smtp_activation_still_requires_an_active_smtp_config(self):
        make_graph(is_active=True)
        with self.assertRaises(ValidationError) as error:
            self.pending("smtp").validate_activation()
        self.assertEqual(list(error.exception.message_dict), ["provider"])

        SMTPProviderConfig.objects.create(name="SMTP", is_active=True, host="smtp.example.com")
        self.pending("smtp").validate_activation()


class EmailServiceConfigGraphDeliveryTest(TestCase):
    def setUp(self):
        self.graph = make_graph(is_active=True)

    def graph_email(self, **overrides):
        values = {"name": "Prod", "is_active": True, "provider": "graph", "from_email": MAILBOX}
        return EmailServiceConfig.objects.create(**values | overrides)

    def test_graph_delivery_is_configured_when_every_piece_is_in_place(self):
        self.assertTrue(self.graph_email().delivery_configured)

    def test_delivery_needs_a_saved_active_email_config_with_a_valid_from_address(self):
        cases = (
            ("never saved", EmailServiceConfig(name="Draft", is_active=True, provider="graph", from_email=MAILBOX)),
            ("inactive", self.graph_email(is_active=False)),
            ("blank from address", self.graph_email(from_email="")),
            ("invalid from address", self.graph_email(from_email="not-an-address")),
        )
        for label, config in cases:
            with self.subTest(label):
                self.assertFalse(config.delivery_configured)

    def test_delivery_needs_an_active_complete_graph_config(self):
        config = self.graph_email()
        rows = (
            ("inactive", {}),
            ("no certificate", {"is_active": True, "certificate": False}),
            ("no tenant", {"is_active": True, "tenant_id": ""}),
            ("no client id", {"is_active": True, "client_id": ""}),
            ("malformed tenant", {"is_active": True, "tenant_id": "common"}),
            ("malformed client id", {"is_active": True, "client_id": "not-a-guid"}),
            ("malformed mailbox", {"is_active": True, "mailbox": "not a mailbox"}),
        )
        for label, overrides in rows:
            store_graph_unvalidated(**overrides)
            with self.subTest(label):
                self.assertFalse(config.delivery_configured)

        MicrosoftGraphProviderConfig.objects.all().delete()
        with self.subTest("no row at all"):
            self.assertFalse(config.delivery_configured)

    def test_other_providers_credentials_do_not_make_graph_delivery_ready(self):
        MicrosoftGraphProviderConfig.objects.all().delete()
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="not-a-real-key", secret_access_key="not-a-real-aws-secret"
        )
        SMTPProviderConfig.objects.create(name="SMTP", is_active=True, host="smtp.example.com")

        self.assertFalse(self.graph_email().delivery_configured)

    def test_graph_credentials_do_not_make_ses_or_smtp_delivery_ready(self):
        for provider in ("ses", "smtp"):
            with self.subTest(provider):
                self.assertFalse(self.graph_email(provider=provider).delivery_configured)

    def test_ses_is_not_configured_for_a_graph_config_even_with_aws_credentials(self):
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="not-a-real-key", secret_access_key="not-a-real-aws-secret"
        )

        self.assertFalse(self.graph_email().ses_configured)
        self.assertTrue(self.graph_email(provider="ses").ses_configured)


class EmailServiceConfigDeliverySummaryTest(TestCase):
    def email(self, provider, **overrides):
        values = {"name": "Prod", "is_active": True, "provider": provider, "from_email": MAILBOX}
        return EmailServiceConfig.objects.create(**values | overrides)

    def test_graph_summary_names_the_sender_mailbox(self):
        make_graph(is_active=True, mailbox="shared@example.com")

        self.assertEqual(self.email("graph").delivery_summary, "Microsoft Graph (shared@example.com)")

    def test_graph_summary_falls_back_to_the_from_address_without_a_mailbox(self):
        make_graph(is_active=True, mailbox="")

        self.assertEqual(
            self.email("graph", from_email="noreply@example.com").delivery_summary,
            "Microsoft Graph (noreply@example.com)",
        )

    def test_ses_summary_names_the_region(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="not-a-real-key",
            secret_access_key="not-a-real-aws-secret",
            default_region="eu-west-1",
        )

        self.assertEqual(self.email("ses").delivery_summary, "AWS SES (eu-west-1)")

    def test_smtp_summary_names_the_host_and_port(self):
        SMTPProviderConfig.objects.create(name="SMTP", is_active=True, host="smtp.example.com", port=2525)

        self.assertEqual(self.email("smtp").delivery_summary, "SMTP (smtp.example.com:2525)")

    def test_unconfigured_delivery_says_so_for_every_provider(self):
        for provider in ("ses", "smtp", "graph"):
            with self.subTest(provider):
                self.assertEqual(self.email(provider).delivery_summary, "Not configured")
        self.assertEqual(EmailServiceConfig().delivery_summary, "Not configured")

    def test_summaries_never_include_credentials(self):
        make_graph(is_active=True)
        summary = self.email("graph").delivery_summary

        for line in private_key_lines():
            self.assertNotIn(line, summary)
        self.assertNotIn(CLIENT_ID, summary)
        self.assertNotIn(TENANT_ID, summary)

    def test_str_uses_the_provider_label(self):
        config = self.email("graph")
        self.assertEqual(str(config), "Prod: Microsoft Graph not configured (active)")

        make_graph(is_active=True)
        self.assertEqual(str(config), "Prod: Microsoft Graph (active)")
