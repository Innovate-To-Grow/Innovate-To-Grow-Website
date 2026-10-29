"""The site-side mailbox scope: ``access.credential_for`` / ``require_mailbox`` and the registry's send checks."""

from types import SimpleNamespace

from django.test import TestCase

from apps.core.models import MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.services.email import GraphProvider, PermanentEmailDeliveryError, resolve_provider
from apps.core.services.email.graph import GraphScopeError
from apps.core.services.email.graph.access import READ, SEND, credential_for, require_mailbox
from apps.core.tests.graph_helpers import certificate_pair, create_graph_config, grant
from apps.core.tests.services.test_email_graph import CLIENT_ID, CLIENT_SECRET, TENANT_ID, GraphFixtureMixin

Permission = MicrosoftGraphMailboxScope.Permission
SENDER = "i2g@contoso.com"
OTHER = "other@contoso.com"


def secret_values(**overrides):
    values = {"name": "Graph", "is_active": True, "tenant_id": TENANT_ID, "client_id": CLIENT_ID}
    return {**values, "client_secret": CLIENT_SECRET, **overrides}


def certificate_values(**overrides):
    certificate, key = certificate_pair()
    values = secret_values(client_secret="", auth_method=MicrosoftGraphProviderConfig.AuthMethod.CERTIFICATE)
    return {**values, "certificate": certificate, "private_key": key, **overrides}


class CredentialForTests(TestCase):
    def test_client_secret_config(self):
        config = create_graph_config(**secret_values())

        credential = credential_for(config)

        self.assertFalse(credential.uses_certificate)
        self.assertEqual((credential.tenant_id, credential.client_id), (TENANT_ID, CLIENT_ID))
        self.assertEqual(credential.client_secret, CLIENT_SECRET)
        self.assertEqual((credential.private_key_pem, credential.certificate_thumbprint), ("", ""))

    def test_certificate_config_uses_the_key_and_never_the_secret(self):
        config = create_graph_config(**certificate_values(client_secret="left-over-secret"))

        credential = credential_for(config)

        self.assertTrue(credential.uses_certificate)
        self.assertEqual(credential.private_key_pem, config.private_key)
        self.assertEqual(credential.certificate_thumbprint, config.certificate_thumbprint)
        self.assertEqual(credential.client_secret, "")


class RequireMailboxTests(TestCase):
    def setUp(self):
        self.config = create_graph_config(scope=(SENDER,), permission=Permission.SEND, **secret_values())
        grant(self.config, "reader@contoso.com", permission=Permission.READ)

    def test_returns_the_mailbox_when_granted(self):
        self.assertEqual(require_mailbox(self.config, SENDER, SEND), SENDER)
        self.assertEqual(require_mailbox(self.config, "reader@contoso.com", READ), "reader@contoso.com")

    def test_scope_matching_is_case_insensitive(self):
        self.assertEqual(require_mailbox(self.config, " I2G@Contoso.com ", SEND), " I2G@Contoso.com ")

    def test_refuses_the_wrong_permission(self):
        with self.assertRaisesMessage(GraphScopeError, f"may not read {SENDER}"):
            require_mailbox(self.config, SENDER, READ)
        with self.assertRaisesMessage(GraphScopeError, "may not send as reader@contoso.com"):
            require_mailbox(self.config, "reader@contoso.com", SEND)

    def test_refuses_mailboxes_outside_the_scope_and_empty_values(self):
        with self.assertRaisesMessage(GraphScopeError, "not in the configured mailbox scope"):
            require_mailbox(self.config, OTHER, SEND)
        with self.assertRaisesMessage(GraphScopeError, "an empty mailbox"):
            require_mailbox(self.config, "", SEND)

    def test_scope_error_is_permanent(self):
        self.assertTrue(issubclass(GraphScopeError, PermanentEmailDeliveryError))

    def test_an_unsaved_config_allows_nothing(self):
        with self.assertRaises(GraphScopeError):
            require_mailbox(MicrosoftGraphProviderConfig(), SENDER, SEND)


class GraphFactoryScopeTests(GraphFixtureMixin, TestCase):
    def service_config(self, from_email=SENDER):
        return SimpleNamespace(provider="graph", from_email=from_email, from_name="Innovate to Grow")

    def assert_refused(self, service_config):
        with self.assertRaises(GraphScopeError):
            resolve_provider(service_config)
        self.assertEqual(self.fake.requests, [])

    def test_sender_and_from_in_scope_build_a_provider(self):
        create_graph_config(scope=(SENDER, OTHER), permission=Permission.SEND, **secret_values(mailbox=SENDER))

        provider = resolve_provider(self.service_config(from_email=OTHER))

        self.assertIsInstance(provider, GraphProvider)
        self.assertEqual((provider.mailbox, provider.from_email), (SENDER, OTHER))
        self.assertEqual(self.fake.requests, [])

    def test_mailbox_is_normalized_from_the_from_address(self):
        create_graph_config(scope=(SENDER,), **secret_values())

        self.assertEqual(resolve_provider(self.service_config(from_email="I2G@Contoso.com")).mailbox, SENDER)

    def test_from_address_outside_the_scope_is_refused(self):
        create_graph_config(scope=(SENDER,), **secret_values(mailbox=SENDER))

        self.assert_refused(self.service_config(from_email=OTHER))

    def test_sending_mailbox_outside_the_scope_is_refused(self):
        create_graph_config(scope=(OTHER,), **secret_values(mailbox=SENDER))

        self.assert_refused(self.service_config(from_email=OTHER))

    def test_read_only_scope_is_refused(self):
        create_graph_config(scope=(SENDER,), permission=Permission.READ, **secret_values())

        self.assert_refused(self.service_config())

    def test_config_without_any_scope_is_not_configured(self):
        create_graph_config(**secret_values())

        with self.assertRaisesMessage(PermanentEmailDeliveryError, "missing or invalid"):
            resolve_provider(self.service_config())
        self.assertEqual(self.fake.requests, [])

    def test_certificate_config_builds_a_certificate_provider(self):
        config = create_graph_config(scope=(SENDER,), **certificate_values())

        provider = resolve_provider(self.service_config())

        self.assertTrue(provider.credential.uses_certificate)
        self.assertEqual(provider.credential.certificate_thumbprint, config.certificate_thumbprint)
        self.assertEqual(provider.credential.client_secret, "")
