from botocore.config import Config
from django.test import TestCase

from apps.core.models import EmailServiceConfig, MicrosoftGraphProviderConfig
from apps.core.services.email import (
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    deliver_email,
)
from apps.core.tests.services.graph.provider.test_email_graph import (
    PROVIDER_LOGGER,
    GraphFixtureMixin,
    graph_response,
    sent_mime,
    simple_message,
)
from apps.core.tests.services.graph.transport.test_email_graph_registry import create_graph_config


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
