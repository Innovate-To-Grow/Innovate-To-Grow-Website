"""The site-side mailbox scope: ``access.credential_for`` / ``require_mailbox`` and the registry's send checks."""

from types import SimpleNamespace

from django.test import TestCase

from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.services.email import GraphProvider, PermanentEmailDeliveryError, resolve_provider
from apps.core.services.email.graph import GraphScopeError
from apps.core.services.email.graph.access import READ, SEND, credential_for, require_mailbox
from apps.core.tests.graph_helpers import create_graph_config, grant, install_test_certificate
from apps.core.tests.services.test_email_graph import CLIENT_ID, TENANT_ID, GraphFixtureMixin

Permission = MicrosoftGraphMailboxScope.Permission
SENDER = "i2g@contoso.com"
OTHER = "other@contoso.com"
OTHER_CLIENT_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"


def config_values(**overrides):
    return {"name": "Graph", "is_active": True, "tenant_id": TENANT_ID, "client_id": CLIENT_ID, **overrides}


class CredentialForTests(TestCase):
    def test_the_credential_pins_the_current_certificate_and_holds_no_key(self):
        config = create_graph_config(**config_values())
        certificate = config.current_certificate

        credential = credential_for(config)

        self.assertEqual((credential.tenant_id, credential.client_id), (TENANT_ID, CLIENT_ID))
        self.assertEqual(credential.x5t_s256, certificate.x5t_s256)
        self.assertEqual(credential.public_key_sha256, certificate.public_key_sha256)
        self.assertEqual(
            (credential.key_arn, credential.key_version_id), (certificate.store_arn, certificate.store_version_id)
        )
        self.assertNotIn("PRIVATE", repr(credential))

    def test_no_usable_current_certificate_is_refused_without_any_request(self):
        cases = {
            "none installed": {},
            "expired": {"days_valid": -1, "not_before_days": -30},
            "not valid yet": {"not_before_days": 2},
            "previous only": {"state": MicrosoftGraphCertificate.State.PREVIOUS},
        }
        for label, options in cases.items():
            with self.subTest(label):
                config = create_graph_config(certificate=False, **config_values(is_active=False))
                if options:
                    install_test_certificate(config, **options)

                with self.assertRaisesMessage(PermanentEmailDeliveryError, "No usable Microsoft Graph certificate"):
                    credential_for(config)

    def test_a_certificate_tested_for_another_app_is_not_used(self):
        config = create_graph_config(**config_values())
        MicrosoftGraphCertificate.objects.filter(config=config).update(client_id=OTHER_CLIENT_ID)

        with self.assertRaises(PermanentEmailDeliveryError):
            credential_for(config)


class RequireMailboxTests(TestCase):
    def setUp(self):
        self.config = create_graph_config(scope=(SENDER,), permission=Permission.SEND, **config_values())
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
        create_graph_config(scope=(SENDER, OTHER), permission=Permission.SEND, **config_values(mailbox=SENDER))

        provider = resolve_provider(self.service_config(from_email=OTHER))

        self.assertIsInstance(provider, GraphProvider)
        self.assertEqual((provider.mailbox, provider.from_email), (SENDER, OTHER))
        self.assertEqual(self.fake.requests, [])

    def test_mailbox_is_normalized_from_the_from_address(self):
        create_graph_config(scope=(SENDER,), **config_values())

        self.assertEqual(resolve_provider(self.service_config(from_email="I2G@Contoso.com")).mailbox, SENDER)

    def test_from_address_outside_the_scope_is_refused(self):
        create_graph_config(scope=(SENDER,), **config_values(mailbox=SENDER))

        self.assert_refused(self.service_config(from_email=OTHER))

    def test_sending_mailbox_outside_the_scope_is_refused(self):
        create_graph_config(scope=(OTHER,), **config_values(mailbox=SENDER))

        self.assert_refused(self.service_config(from_email=OTHER))

    def test_read_only_scope_is_refused(self):
        create_graph_config(scope=(SENDER,), permission=Permission.READ, **config_values())

        self.assert_refused(self.service_config())

    def test_config_without_any_scope_is_not_configured(self):
        create_graph_config(**config_values())

        with self.assertRaisesMessage(PermanentEmailDeliveryError, "missing or invalid"):
            resolve_provider(self.service_config())
        self.assertEqual(self.fake.requests, [])

    def test_the_provider_signs_with_the_current_certificate(self):
        config = create_graph_config(scope=(SENDER,), **config_values())

        provider = resolve_provider(self.service_config())

        self.assertEqual(provider.credential, credential_for(config))
        self.assertEqual(provider.credential.x5t_s256, config.current_certificate.x5t_s256)
