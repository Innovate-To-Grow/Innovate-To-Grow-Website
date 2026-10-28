"""Registry factory and delivery facade for the ``graph`` provider.

These tests need the database because the factory loads the active ``MicrosoftGraphProviderConfig`` row.
"""

from types import SimpleNamespace

from botocore.config import Config
from django.test import TestCase

from apps.core.models import EmailServiceConfig, MicrosoftGraphProviderConfig
from apps.core.services.email import (
    GraphProvider,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    deliver_email,
    resolve_provider,
)
from apps.core.services.email.registry import register_provider
from apps.core.tests.services.test_email_graph import (
    CLIENT_ID,
    CLIENT_SECRET,
    PROVIDER_LOGGER,
    TENANT_ID,
    GraphFixtureMixin,
    graph_response,
    sent_mime,
    simple_message,
)


def create_graph_config(**overrides):
    values = {
        "name": "Graph",
        "is_active": True,
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    return MicrosoftGraphProviderConfig.objects.create(**{**values, **overrides})


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
        self.assertEqual((provider.tenant_id, provider.client_id), (TENANT_ID, CLIENT_ID))
        self.assertEqual(provider.client_secret, CLIENT_SECRET)
        self.assertEqual((provider.from_email, provider.from_name), ("noreply@ucmerced.edu", "Innovate to Grow"))

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

    def test_an_active_config_without_a_secret_is_unconfigured(self):
        config = create_graph_config()
        MicrosoftGraphProviderConfig.objects.filter(pk=config.pk).update(client_secret="")

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

                self.assertNotIn(CLIENT_SECRET, str(caught.exception))

    def test_an_invalid_from_email_fallback_is_rejected(self):
        create_graph_config(mailbox="")

        with self.assertRaisesMessage(PermanentEmailDeliveryError, "configuration is invalid"):
            resolve_provider(SimpleNamespace(provider="graph", from_email="not-an-address", from_name=""))

    def test_the_graph_provider_cannot_be_registered_twice(self):
        with self.assertRaisesMessage(ValueError, "already registered"):
            register_provider("graph", lambda config: None)


class GraphDeliveryFacadeTests(GraphFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.service = EmailServiceConfig.objects.create(
            name="Graph",
            is_active=True,
            provider="graph",
            from_email="noreply@ucmerced.edu",
            from_name="Innovate to Grow",
        )
        create_graph_config()

    def test_deliver_email_sends_through_graph_with_the_active_configurations(self):
        result = deliver_email(simple_message())

        self.assertEqual(result.provider, "graph")
        self.assertTrue(result.accepted)
        self.assertEqual(
            [request.host for request in self.fake.requests], ["login.microsoftonline.com", "graph.microsoft.com"]
        )
        request = self.fake.send_requests[0]
        self.assertEqual(request.path, "/v1.0/users/noreply@ucmerced.edu/sendMail")
        mime = sent_mime(request)
        self.assertEqual(mime["From"], "Innovate to Grow <noreply@ucmerced.edu>")
        self.assertEqual(result.message_id, str(mime["Message-ID"]))

    def test_a_configured_mailbox_sends_as_that_mailbox_but_keeps_the_from_address(self):
        MicrosoftGraphProviderConfig.objects.update(mailbox="shared@contoso.com")

        deliver_email(simple_message())

        request = self.fake.send_requests[0]
        self.assertEqual(request.path, "/v1.0/users/shared@contoso.com/sendMail")
        self.assertEqual(sent_mime(request)["From"], "Innovate to Grow <noreply@ucmerced.edu>")

    def test_the_callback_runs_between_the_token_and_the_send_and_ses_options_are_ignored(self):
        calls = []
        self.fake.log = calls

        deliver_email(
            simple_message(),
            before_provider_call=lambda: calls.append("callback"),
            retry_config=Config(retries={"total_max_attempts": 1}),
            configuration_set="events",
        )

        self.assertEqual(calls, ["token", "callback", "sendMail"])

    def test_an_explicit_service_config_is_honoured(self):
        EmailServiceConfig.objects.update(is_active=False)

        result = deliver_email(simple_message(), config=self.service)

        self.assertEqual(result.provider, "graph")

    def test_failures_keep_their_classification_and_retry_after(self):
        self.script(send=graph_response(429, headers={"retry-after": "30"}))

        with (
            self.assertLogs(PROVIDER_LOGGER, level="WARNING"),
            self.assertRaises(TransientEmailDeliveryError) as caught,
        ):
            deliver_email(simple_message())

        self.assertEqual(caught.exception.retry_after, 30.0)

    def test_an_inactive_email_service_config_is_permanent_and_sends_nothing(self):
        EmailServiceConfig.objects.update(is_active=False)

        with self.assertRaisesMessage(PermanentEmailDeliveryError, "No active email service configuration"):
            deliver_email(simple_message())

        self.assertEqual(self.fake.requests, [])

    def test_a_missing_graph_config_is_permanent_and_sends_nothing(self):
        MicrosoftGraphProviderConfig.objects.all().delete()

        with self.assertRaisesMessage(PermanentEmailDeliveryError, "missing or invalid"):
            deliver_email(simple_message())

        self.assertEqual(self.fake.requests, [])
