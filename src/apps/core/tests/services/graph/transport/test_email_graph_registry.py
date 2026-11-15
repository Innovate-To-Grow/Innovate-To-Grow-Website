"""Registry factory and delivery facade for the ``graph`` provider.

These tests need the database because the factory loads the active ``MicrosoftGraphProviderConfig`` row.
"""

from types import SimpleNamespace

from botocore.config import Config
from django.test import TestCase

from apps.core.models import MicrosoftGraphProviderConfig
from apps.core.services.email import (
    GraphProvider,
    PermanentEmailDeliveryError,
    resolve_provider,
)
from apps.core.services.email.registry import register_provider
from apps.core.tests import graph_helpers
from apps.core.tests.services.graph.provider.test_email_graph import (
    CLIENT_ID,
    TENANT_ID,
    GraphFixtureMixin,
    simple_message,
)

# Every sender these tests use is in scope; the scope rules have their own tests.
SCOPE = ("noreply@ucmerced.edu", "shared@contoso.com")


def create_graph_config(**overrides):
    values = {
        "name": "Graph",
        "is_active": True,
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
    }
    return graph_helpers.create_graph_config(scope=SCOPE, **{**values, **overrides})


class GraphProviderFactoryTests(GraphFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.service_config = SimpleNamespace(
            provider="graph", from_email="noreply@ucmerced.edu", from_name="Innovate to Grow"
        )

    def test_builds_a_graph_provider_from_the_active_config(self):
        create_graph_config()

        provider = resolve_provider(self.service_config)

        self.assertIsInstance(provider, GraphProvider)
        self.assertEqual(provider.name, "graph")
        self.assertEqual((provider.credential.tenant_id, provider.credential.client_id), (TENANT_ID, CLIENT_ID))
        self.assertEqual(provider.credential.x5t_s256, MicrosoftGraphProviderConfig.load().current_certificate.x5t_s256)
        self.assertEqual((provider.from_email, provider.from_name), ("noreply@ucmerced.edu", "Innovate to Grow"))
        self.assertEqual(provider.max_recipients, 500)

    def test_the_configured_recipients_per_message_limit_reaches_the_provider(self):
        create_graph_config(max_recipients_per_message=2)

        provider = resolve_provider(self.service_config)

        self.assertEqual(provider.max_recipients, 2)
        too_many = simple_message(to=("a@example.com", "b@example.com", "c@example.com"))
        with self.assertRaisesMessage(PermanentEmailDeliveryError, "allows at most 2 per message"):
            provider.send(too_many)

    def test_mailbox_falls_back_to_the_from_email(self):
        create_graph_config(mailbox="")

        self.assertEqual(resolve_provider(self.service_config).mailbox, "noreply@ucmerced.edu")

    def test_an_explicit_mailbox_wins_over_the_from_email(self):
        create_graph_config(mailbox="shared@contoso.com")

        provider = resolve_provider(self.service_config)

        self.assertEqual(provider.mailbox, "shared@contoso.com")
        self.assertEqual(provider.from_email, "noreply@ucmerced.edu")

    def test_provider_name_matching_ignores_case_and_surrounding_whitespace(self):
        create_graph_config()

        padded = SimpleNamespace(provider=" Graph ", from_email="noreply@ucmerced.edu", from_name="")

        self.assertIsInstance(resolve_provider(padded), GraphProvider)

    def test_ses_options_are_ignored(self):
        create_graph_config()

        provider = resolve_provider(
            self.service_config,
            retry_config=Config(retries={"total_max_attempts": 1}),
            configuration_set="events",
        )

        self.assertIsInstance(provider, GraphProvider)

    def test_a_missing_config_is_permanent(self):
        with self.assertRaisesMessage(PermanentEmailDeliveryError, "missing or invalid"):
            resolve_provider(self.service_config)

    def test_an_inactive_config_is_never_used_as_a_fallback(self):
        create_graph_config(is_active=False)

        with self.assertRaisesMessage(PermanentEmailDeliveryError, "missing or invalid"):
            resolve_provider(self.service_config)

    def test_an_active_config_without_a_current_certificate_is_unconfigured(self):
        config = create_graph_config()
        config.certificates.update(state="removed")

        with self.assertRaisesMessage(PermanentEmailDeliveryError, "missing or invalid"):
            resolve_provider(self.service_config)

    def test_rows_with_invalid_identifiers_stored_outside_validation_are_not_configured(self):
        for field, value in (("tenant_id", "common"), ("client_id", "not-a-guid"), ("mailbox", "not a mailbox")):
            with self.subTest(field):
                MicrosoftGraphProviderConfig.objects.all().delete()
                config = create_graph_config()
                MicrosoftGraphProviderConfig.objects.filter(pk=config.pk).update(**{field: value})

                # is_configured checks the formats too, so readiness gates and the provider agree.
                with self.assertRaisesMessage(PermanentEmailDeliveryError, "missing or invalid") as caught:
                    resolve_provider(self.service_config)

                self.assertNotIn("PRIVATE KEY", str(caught.exception))

    def test_an_invalid_from_email_fallback_is_rejected(self):
        create_graph_config(mailbox="")

        # The scope check refuses it first: an address that is not a mailbox can never be in scope.
        with self.assertRaisesMessage(PermanentEmailDeliveryError, "not in the configured mailbox scope"):
            resolve_provider(SimpleNamespace(provider="graph", from_email="not-an-address", from_name=""))

    def test_the_graph_provider_cannot_be_registered_twice(self):
        with self.assertRaisesMessage(ValueError, "already registered"):
            register_provider("graph", lambda config: None)
