import json
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, SMTPProviderConfig
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import private_key_lines
from apps.core.tests.models.test_graph_go_live_gate import DENY, evidence
from apps.mail.tests.admin.mail_settings_graph.settings.test_mail_settings_admin_graph import (
    FAKE_TOKEN,
    FakeGraphTransport,
    GraphSettingsTestCase,
)


class SummaryChipTests(GraphSettingsTestCase):
    def test_graph_chip_names_the_mailbox_in_the_success_colour(self):
        self.make_graph()
        self.use_provider("graph")

        response = self.client.get(self.summary_url)

        self.assertEqual(response.context["email_provider"], "Microsoft Graph (mailer@example.com)")
        self.assertEqual(response.context["email_provider_color"], "success")
        self.assert_chip(response, "Microsoft Graph (mailer@example.com)", "success")
        self.assert_no_key_material(response.content)

    def test_graph_chip_names_the_from_email_when_no_mailbox_is_set(self):
        self.make_graph(mailbox="")
        self.use_provider("graph")

        response = self.client.get(self.summary_url)

        self.assert_chip(response, "Microsoft Graph (admin@example.com)", "success")

    def test_graph_chip_warns_when_no_graph_config_exists(self):
        self.use_provider("graph")

        response = self.client.get(self.summary_url)

        self.assertEqual(response.context["email_provider_color"], "warning")
        self.assert_chip(response, "Microsoft Graph not configured", "warning")

    def test_graph_chip_warns_when_the_only_graph_config_is_inactive(self):
        self.make_graph(is_active=False)
        self.use_provider("graph")

        response = self.client.get(self.summary_url)

        self.assert_chip(response, "Microsoft Graph not configured", "warning")

    def test_ses_and_smtp_chips_keep_their_text_and_colours(self):
        cases = (
            ("ses", True, "Amazon Simple Email Service (us-west-2)", "success"),
            ("smtp", True, "SMTP (smtp.example.com:587)", "success"),
            ("smtp", False, "SMTP not configured", "warning"),
            ("ses", False, "Amazon Simple Email Service not configured", "warning"),
        )
        for provider, configured, text, colour in cases:
            with self.subTest(provider=provider, configured=configured):
                self.use_provider(provider)
                SMTPProviderConfig.objects.update(is_active=configured and provider == "smtp")
                AWSCredentialConfig.objects.update(access_key_id="test-key" if configured else "")

                response = self.client.get(self.summary_url)

                self.assert_chip(response, text, colour)
                self.assertNotIn("Microsoft Graph", response.context["email_provider"])


class SummaryRateTests(GraphSettingsTestCase):
    def test_graph_shows_the_live_rate_of_its_mailbox(self):
        self.make_graph()
        self.use_provider("graph")

        response = self.client.get(self.summary_url)

        self.assertContains(response, "Send Rate")
        self.assertContains(response, "Now: 24 messages/min · Smart")
        self.assertNotContains(response, "Campaign Send Rate")

    def test_ses_shows_the_live_rate_of_its_account(self):
        response = self.client.get(self.summary_url)

        self.assertContains(response, "recipients/sec · Smart")


class SendTestEmailTests(GraphSettingsTestCase):
    def setUp(self):
        super().setUp()
        self.make_graph()
        self.use_provider("graph")
        self.test_email_url = reverse("admin:mail_settings_test_email")

    def test_test_email_goes_through_graph_and_the_confirmation_names_it(self):
        transport = FakeGraphTransport()

        with patch("apps.core.services.email.graph.transport.post", transport):
            response = self.client.post(self.test_email_url, {"recipient": "ops@example.com"}, follow=True)

        self.assertContains(
            response, "Test email sent to ops@example.com via Microsoft Graph (config: Production Mail)."
        )
        (sent,) = transport.sent
        self.assertEqual(sent.path, "/v1.0/users/mailer@example.com/sendMail")
        self.assertEqual(sent.headers["Authorization"], f"Bearer {FAKE_TOKEN}")
        self.assertEqual(sent.headers["Content-Type"], "text/plain")
        self.assertEqual(transport.sent_mime["To"], "ops@example.com")
        self.assertEqual(transport.sent_mime["From"], "I2G Admin <admin@example.com>")
        self.assert_no_key_material(sent.body)
        self.assert_no_key_material(response.content)
        self.assertNotContains(response, FAKE_TOKEN)

    def test_graph_rejection_is_reported_without_response_details_or_secrets(self):
        body = json.dumps({"error": {"code": "ErrorSendAsDenied", "message": "leaky detail for mailer@example.com"}})
        transport = FakeGraphTransport(HttpResponse(403, {"request-id": "abc12345-def6"}, body.encode()))

        with (
            self.assertLogs("apps.core.services.email.graph.provider", level="WARNING") as logs,
            patch("apps.core.services.email.graph.transport.post", transport),
        ):
            response = self.client.post(self.test_email_url, {"recipient": "ops@example.com"}, follow=True)

        self.assertContains(
            response, "Failed to send test email: Microsoft Graph rejected the request (ErrorSendAsDenied)."
        )
        self.assertEqual(len(transport.sent), 1)
        for leaked in ("leaky detail", FAKE_TOKEN, *private_key_lines()):
            self.assertNotContains(response, leaked)
            self.assertNotIn(leaked, "\n".join(logs.output))


@override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
class GoLiveGateTests(GraphSettingsTestCase):
    """Under the go-live gate (``GRAPH_REQUIRE_ACCESS_EVIDENCE``, on in production)."""

    def test_graph_cannot_be_selected_without_access_check_evidence(self):
        self.make_graph(access_check_deny_mailbox=DENY)

        response = self.client.post(self.edit_url, self.post_data("graph"))

        self.assertEqual(response.status_code, 200)
        [error] = response.context["email_form"].errors["provider"]
        self.assertTrue(error.startswith("Email cannot switch to Microsoft Graph yet: no access check is recorded"))
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")

    def test_graph_can_be_selected_with_a_recent_passing_access_check(self):
        evidence(self.make_graph(access_check_deny_mailbox=DENY))

        response = self.client.post(self.edit_url, self.post_data("graph"))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "graph")

    def test_the_read_only_graph_panel_shows_what_is_missing(self):
        self.make_graph(access_check_deny_mailbox=DENY)

        response = self.client.get(self.edit_url)

        self.assertContains(response, "Go-live evidence:</span>")
        self.assertContains(response, "missing: no access check is recorded for the current certificate")
