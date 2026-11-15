from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    MicrosoftGraphProviderConfig,
    SMTPProviderConfig,
)
from apps.core.tests.models.graph.test_microsoft_graph_config import (
    MAILBOX,
    graph_fields,
    make_graph,
    store_graph_unvalidated,
)


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
