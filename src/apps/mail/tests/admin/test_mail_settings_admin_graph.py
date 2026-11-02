"""The Notification Delivery pages with the Microsoft Graph provider (no network, throwaway certificates only).

The Graph config is read-only here: it is managed on its own admin page (Core app), and this page only selects it
as the provider, which ``EmailServiceConfig.validate_activation`` allows only when it can send.
"""

import base64
import json
import re
from email import message_from_bytes, policy
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, MicrosoftGraphProviderConfig, SMTPProviderConfig
from apps.core.services.email.graph import clear_access_token_cache
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import create_graph_config, private_key_lines
from apps.core.tests.models.test_graph_go_live_gate import DENY, evidence
from apps.event.tests.helpers import make_admin, make_superuser

TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "66666666-7777-8888-9999-000000000000"
OBJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
# The senders these tests submit; the mailbox scope itself is edited on the Graph config admin page.
GRAPH_SCOPE = ("mailer@example.com", "updated@example.com", "old@example.com", "admin@example.com", OBJECT_ID)
FAKE_TOKEN = "not-a-real-token"
# Every Graph input the old page had; none is rendered or accepted any more.
GRAPH_INPUTS = {
    "graph-name": "Hijacked",
    "graph-tenant_id": "99999999-8888-7777-6666-555555555555",
    "graph-client_id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
    "graph-mailbox": "attacker@example.com",
    "graph-messages_per_minute": "30",
    "graph-certificate": "ignored-not-a-credential",
    "graph-private_key": "ignored-not-a-credential",
    "graph-client_secret": "ignored-not-a-credential",
}
GRAPH_CONFIG_URL_NAME = "admin:core_microsoftgraphproviderconfig_change"
PROVIDER_ERROR = (
    "An active Microsoft Graph configuration whose mailbox scope lets the sender mailbox and the From address "
    "send is required before activation."
)
CHIP_COLOURS = {"success": "bg-green-50", "warning": "bg-orange-50"}


def snapshot(instance):
    """Every stored column of *instance* as the database holds it right now."""
    instance.refresh_from_db()
    return {field.attname: getattr(instance, field.attname) for field in instance._meta.concrete_fields}


class _ElementFinder(HTMLParser):
    def __init__(self, element_id):
        super().__init__()
        self.element_id = element_id
        self.attrs = None

    def handle_starttag(self, tag, attrs):
        if dict(attrs).get("id") == self.element_id:
            self.attrs = dict(attrs)


class FakeGraphTransport:
    """Replacement for ``graph.transport.post``: a token on the identity host, a canned answer on the Graph host."""

    def __init__(self, send_response=None):
        self.send_response = send_response or HttpResponse(202, {}, b"")
        self.calls = []

    def __call__(self, host, path, body, headers, *, timeout):
        self.calls.append(SimpleNamespace(host=host, path=path, body=body, headers=headers))
        if host == "login.microsoftonline.com":
            return HttpResponse(200, {}, json.dumps({"access_token": FAKE_TOKEN, "expires_in": 3600}).encode())
        return self.send_response

    @property
    def sent(self):
        return [call for call in self.calls if call.host == "graph.microsoft.com"]

    @property
    def sent_mime(self):
        return message_from_bytes(base64.b64decode(self.sent[-1].body), policy=policy.default)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class GraphSettingsTestCase(TestCase):
    """A superuser, an active SES sender with AWS credentials (still needed for SMS) and a retained SMTP config."""

    def setUp(self):
        clear_access_token_cache()
        self.addCleanup(clear_access_token_cache)
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = EmailServiceConfig.objects.create(
            name="Production Mail",
            is_active=True,
            provider="ses",
            from_email="admin@example.com",
            from_name="I2G Admin",
            max_send_rate=12,
        )
        self.aws_config = AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            sms_from_number="+12065550000",
            sms_message_template="Your I2G code is {code}.",
        )
        self.smtp_config = SMTPProviderConfig.objects.create(
            name="Backup SMTP",
            is_active=True,
            host="smtp.example.com",
            port=587,
            username="mailer",
            password="existing-secret",
            use_tls=True,
        )
        self.edit_url = reverse("admin:mail_settings_edit")
        self.summary_url = reverse("admin:mail_settings")

    def make_graph(self, **overrides):
        values = {
            "name": "Outlook Sender",
            "is_active": True,
            "tenant_id": TENANT_ID,
            "client_id": CLIENT_ID,
            "mailbox": "mailer@example.com",
        }
        return create_graph_config(scope=GRAPH_SCOPE, **{**values, **overrides})

    def use_provider(self, provider):
        self.config.provider = provider
        self.config.save()

    def post_data(self, provider, **extra):
        """The browser's POST body (plus *extra* inputs, such as smuggled Graph fields)."""
        data = {
            "email-name": "Updated Mail",
            "email-is_active": "on",
            "email-provider": provider,
            "email-from_name": "Updated Sender",
            "email-from_email": "updated@example.com",
            "email-max_send_rate": "8",
            "aws-name": "Primary AWS",
            "aws-is_active": "on",
            "aws-access_key_id": "test-key",
            "aws-secret_access_key": "test-secret",
            "aws-default_region": "us-west-2",
            "aws-sms_message_template": "Your I2G code is {code}.",
        }
        if provider == "smtp":
            data.update(
                {
                    "smtp-name": "Updated SMTP",
                    "smtp-is_active": "on",
                    "smtp-host": "mail.example.com",
                    "smtp-port": "587",
                    "smtp-username": "mailer",
                    "smtp-password": "",
                    "smtp-use_tls": "on",
                    "smtp-timeout": "30",
                }
            )
        return data | extra

    def state(self):
        """Every delivery row as stored, to prove that a rejected request changed nothing."""
        return {
            "email": snapshot(self.config),
            "aws": snapshot(self.aws_config),
            "smtp": snapshot(self.smtp_config),
            "graph": [snapshot(row) for row in MicrosoftGraphProviderConfig.objects.order_by("created_at")],
        }

    def assert_no_key_material(self, content):
        text = content.decode() if isinstance(content, bytes) else content
        self.assertNotIn("PRIVATE KEY", text)
        for line in private_key_lines():
            self.assertNotIn(line, text)

    def panel_attrs(self, response, panel_id):
        finder = _ElementFinder(panel_id)
        finder.feed(response.content.decode())
        self.assertIsNotNone(finder.attrs, f"#{panel_id} is not rendered")
        return finder.attrs

    def chip_classes(self, response, text):
        match = re.search(rf'<span class="([^"]*)">\s*{re.escape(text)}\s*</span>', response.content.decode())
        self.assertIsNotNone(match, f"no status chip reads {text!r}")
        return match.group(1)

    def assert_chip(self, response, text, colour):
        classes = self.chip_classes(response, text)
        self.assertIn(CHIP_COLOURS[colour], classes)
        self.assertNotIn(CHIP_COLOURS["warning" if colour == "success" else "success"], classes)


class EditPageRenderingTests(GraphSettingsTestCase):
    def test_graph_provider_opens_the_read_only_graph_panel_and_hides_the_smtp_panel(self):
        graph = self.make_graph()
        self.use_provider("graph")

        response = self.client.get(self.edit_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["graph_enabled"])
        self.assertNotIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertIn("hidden", self.panel_attrs(response, "smtp-provider-settings"))
        self.assertContains(response, "Microsoft Graph Provider")
        self.assertNotContains(response, 'name="graph-')
        certificate = graph.current_certificate
        for value in (TENANT_ID, CLIENT_ID, "mailer@example.com", certificate.sha1_thumbprint, "Expires in "):
            self.assertContains(response, value)
        self.assertContains(response, "Thumbprint (SHA-1, as shown in Entra)")
        self.assertContains(response, '<option value="graph" selected>Microsoft Graph</option>', html=True)
        self.assertTrue(all(field.disabled for field in response.context["smtp_form"].fields.values()))
        self.assert_no_key_material(response.content)

    def test_ses_provider_hides_both_provider_panels(self):
        self.make_graph()

        response = self.client.get(self.edit_url)

        self.assertFalse(response.context["graph_enabled"])
        self.assertIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertIn("hidden", self.panel_attrs(response, "smtp-provider-settings"))
        self.assertContains(response, '<option value="ses" selected>AWS SES</option>', html=True)
        self.assertContains(response, '<option value="graph">Microsoft Graph</option>', html=True)

    def test_smtp_provider_opens_the_smtp_panel_and_hides_the_graph_panel(self):
        self.make_graph()
        self.use_provider("smtp")

        response = self.client.get(self.edit_url)

        self.assertTrue(response.context["smtp_enabled"])
        self.assertNotIn("hidden", self.panel_attrs(response, "smtp-provider-settings"))
        self.assertIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertNotContains(response, "existing-secret")

    def test_superusers_and_core_staff_get_a_link_to_the_graph_config_but_no_certificate_actions(self):
        graph = self.make_graph()
        config_url = reverse(GRAPH_CONFIG_URL_NAME, args=[graph.pk])
        for user in (self.admin_user, make_admin(apps=["mail", "core"], email="core-mail@example.com")):
            with self.subTest(superuser=user.is_superuser):
                self.client.force_login(user)

                response = self.client.get(self.edit_url)

                self.assertContains(response, config_url)
                self.assertNotContains(response, f"{config_url.removesuffix('change/')}certificate/install/")

    def test_mail_only_staff_see_the_graph_config_without_any_link_to_change_it(self):
        graph = self.make_graph()
        self.use_provider("graph")
        self.client.force_login(make_admin(apps=["mail"], email="mail-only@example.com"))

        response = self.client.get(self.edit_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, graph.current_certificate.sha1_thumbprint)
        self.assertNotContains(response, "/admin/core/microsoftgraphproviderconfig/")
        self.assertContains(response, "Changing the Microsoft Graph configuration needs the Core app")

    def test_without_a_graph_config_the_panel_says_so_and_links_to_the_add_page(self):
        self.use_provider("graph")

        response = self.client.get(self.edit_url)

        self.assertContains(response, "No Microsoft Graph configuration is active.")
        self.assertContains(response, reverse("admin:core_microsoftgraphproviderconfig_add"))
        self.assertNotContains(response, 'id="graph-certificate-panel"')


class SelectingGraphTests(GraphSettingsTestCase):
    def test_graph_cannot_be_selected_without_a_graph_config(self):
        response = self.client.post(self.edit_url, self.post_data("graph"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["email_form"].errors["provider"], [PROVIDER_ERROR])
        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")

    def test_selecting_graph_activates_the_provider_and_leaves_the_graph_config_untouched(self):
        graph = self.make_graph()
        before = snapshot(graph)

        response = self.client.post(self.edit_url, self.post_data("graph"))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.config.refresh_from_db()
        self.assertEqual((self.config.provider, self.config.from_email), ("graph", "updated@example.com"))
        self.assertTrue(self.config.delivery_configured)
        self.assertEqual(snapshot(graph), before)
        self.assertEqual(EmailServiceConfig.objects.count(), 1)

    def test_saving_reports_success_and_the_summary_names_the_graph_mailbox(self):
        self.make_graph()
        response = self.client.post(self.edit_url, self.post_data("graph"), follow=True)

        self.assertContains(response, "Notification delivery settings saved.")
        self.assert_chip(response, "Microsoft Graph (mailer@example.com)", "success")

    def test_graph_inputs_posted_here_change_nothing(self):
        graph = self.make_graph()
        before = snapshot(graph)
        certificate = graph.current_certificate

        for provider in ("graph", "ses", "smtp"):
            with self.subTest(provider=provider):
                response = self.client.post(self.edit_url, self.post_data(provider, **GRAPH_INPUTS))

                self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
                self.assertEqual(snapshot(graph), before)
                self.assertEqual(graph.current_certificate, certificate)

    def test_graph_without_a_mailbox_falls_back_to_the_from_email(self):
        self.make_graph(mailbox="")
        response = self.client.post(self.edit_url, self.post_data("graph"), follow=True)

        self.assert_chip(response, "Microsoft Graph (updated@example.com)", "success")

    def test_selecting_graph_retains_the_aws_credentials_used_for_sms(self):
        self.make_graph()
        before = snapshot(self.aws_config)

        self.client.post(self.edit_url, self.post_data("graph"))

        after = snapshot(self.aws_config)
        for row in (before, after):
            row.pop("updated_at")
        self.assertEqual(after, before)
        self.assertTrue(AWSCredentialConfig.load().sns_configured)

    def test_round_trip_through_every_provider_keeps_the_graph_config(self):
        graph = self.make_graph()
        before = snapshot(graph)
        for provider in ("graph", "ses", "smtp", "graph"):
            with self.subTest(provider=provider):
                response = self.client.post(self.edit_url, self.post_data(provider))

                self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
                self.config.refresh_from_db()
                self.assertEqual(self.config.provider, provider)
                self.assertEqual(snapshot(graph), before)

    def test_selecting_smtp_still_saves_the_smtp_config(self):
        self.make_graph()

        response = self.client.post(self.edit_url, self.post_data("smtp"))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.smtp_config.refresh_from_db()
        self.assertEqual((self.smtp_config.name, self.smtp_config.host), ("Updated SMTP", "mail.example.com"))
        self.assertEqual(self.smtp_config.password, "existing-secret")


class RejectedGraphSelectionTests(GraphSettingsTestCase):
    def assert_rejected(self, response, before):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["email_form"].errors["provider"], [PROVIDER_ERROR])
        self.assertContains(response, PROVIDER_ERROR)
        self.assertTrue(response.context["graph_enabled"])
        self.assertNotIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertEqual(self.state(), before)
        self.assert_no_key_material(response.content)

    def test_an_inactive_graph_config_cannot_be_selected(self):
        self.make_graph(is_active=False)
        before = self.state()

        self.assert_rejected(self.client.post(self.edit_url, self.post_data("graph")), before)

    def test_a_graph_config_without_a_certificate_cannot_be_selected(self):
        self.make_graph(certificate=False)
        before = self.state()

        self.assert_rejected(self.client.post(self.edit_url, self.post_data("graph")), before)

    def test_a_from_address_outside_the_scope_cannot_be_selected(self):
        self.make_graph()
        before = self.state()

        data = self.post_data("graph") | {"email-from_email": "outside@example.com"}

        self.assert_rejected(self.client.post(self.edit_url, data), before)


class AccessControlTests(GraphSettingsTestCase):
    def test_staff_without_mail_access_cannot_read_or_change_the_graph_settings(self):
        self.make_graph()
        self.client.force_login(make_admin(apps=["event"], email="outsider@example.com"))
        before = self.state()

        self.assertEqual(self.client.get(self.edit_url).status_code, 403)
        self.assertEqual(self.client.post(self.edit_url, self.post_data("graph")).status_code, 403)
        self.assertEqual(self.client.get(self.summary_url).status_code, 403)
        self.assertEqual(self.state(), before)

    def test_mail_only_staff_can_select_a_ready_graph_config_but_not_change_it(self):
        graph = self.make_graph()
        before = snapshot(graph)
        self.client.force_login(make_admin(apps=["mail"], email="mail-only@example.com"))

        response = self.client.post(self.edit_url, self.post_data("graph", **GRAPH_INPUTS))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.assertEqual(snapshot(graph), before)
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "graph")
        self.assertEqual(self.client.get(reverse(GRAPH_CONFIG_URL_NAME, args=[graph.pk])).status_code, 403)


class SummaryGraphPanelTests(GraphSettingsTestCase):
    def test_the_summary_shows_the_graph_panel_while_graph_is_selected(self):
        graph = self.make_graph()
        self.use_provider("graph")

        response = self.client.get(self.summary_url)

        self.assertContains(response, 'id="graph-provider-summary"')
        self.assertContains(response, graph.current_certificate.sha1_thumbprint)
        self.assertContains(response, "mailer@example.com &mdash; Send and read")
        self.assert_no_key_material(response.content)

    def test_the_summary_leaves_the_graph_panel_out_for_other_providers(self):
        self.make_graph()

        self.assertNotContains(self.client.get(self.summary_url), 'id="graph-provider-summary"')


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
