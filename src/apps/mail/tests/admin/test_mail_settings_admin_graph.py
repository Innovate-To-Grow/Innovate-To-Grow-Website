"""The Notification Delivery pages with the Microsoft Graph provider (no network, throwaway certificates only)."""

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
from apps.event.tests.helpers import make_admin, make_superuser

TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "66666666-7777-8888-9999-000000000000"
OBJECT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
# The senders these tests submit; the mailbox scope itself is edited on the Graph config admin page.
GRAPH_SCOPE = ("mailer@example.com", "updated@example.com", "old@example.com", "admin@example.com", OBJECT_ID)
FAKE_TOKEN = "not-a-real-token"
GRAPH_FIELDS = ("name", "is_active", "tenant_id", "client_id", "mailbox", "messages_per_minute")
# Credential inputs this page must never render or accept: certificates are installed on the Graph config's page.
CREDENTIAL_INPUTS = ("graph-client_secret", "graph-private_key", "graph-certificate", "graph-auth_method")
PROVIDER_ERROR = (
    "An active Microsoft Graph configuration whose mailbox scope lets the sender mailbox and the From address "
    "send is required before activation."
)
CHIP_COLOURS = {"success": "bg-green-50", "warning": "bg-yellow-50"}


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
            "messages_per_minute": 24,
        }
        return create_graph_config(scope=GRAPH_SCOPE, **{**values, **overrides})

    def use_provider(self, provider):
        self.config.provider = provider
        self.config.save()

    def post_data(self, provider, **graph):
        """The browser's POST body. ``graph`` overrides ``graph-*`` values; ``None`` leaves the input out."""
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
        if provider == "graph":
            data.update(
                {
                    "graph-name": "Outlook Sender",
                    "graph-is_active": "on",
                    "graph-tenant_id": TENANT_ID,
                    "graph-client_id": CLIENT_ID,
                    "graph-mailbox": "mailer@example.com",
                    "graph-messages_per_minute": "20",
                }
            )
            for name, value in graph.items():
                if value is None:
                    data.pop(f"graph-{name}", None)
                else:
                    data[f"graph-{name}"] = value
        return data

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
    def test_graph_provider_opens_the_graph_panel_and_hides_the_smtp_panel(self):
        self.make_graph()
        self.use_provider("graph")

        response = self.client.get(self.edit_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["graph_enabled"])
        self.assertFalse(response.context["smtp_enabled"])
        self.assertNotIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertIn("hidden", self.panel_attrs(response, "smtp-provider-settings"))
        self.assertContains(response, "Microsoft Graph Provider")
        for name in GRAPH_FIELDS:
            self.assertContains(response, f'name="graph-{name}"')
        self.assertContains(response, '<option value="graph" selected>Microsoft Graph</option>', html=True)
        self.assertFalse(any(field.disabled for field in response.context["graph_form"].fields.values()))
        self.assertTrue(all(field.disabled for field in response.context["smtp_form"].fields.values()))

    def test_ses_provider_hides_both_provider_panels_and_disables_their_inputs(self):
        self.make_graph()

        response = self.client.get(self.edit_url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["graph_enabled"])
        self.assertFalse(response.context["smtp_enabled"])
        self.assertIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertIn("hidden", self.panel_attrs(response, "smtp-provider-settings"))
        self.assertIn("disabled", str(response.context["graph_form"]["tenant_id"]))
        self.assertContains(response, '<option value="ses" selected>AWS SES</option>', html=True)
        self.assertContains(response, '<option value="smtp">SMTP</option>', html=True)
        self.assertContains(response, '<option value="graph">Microsoft Graph</option>', html=True)

    def test_smtp_provider_opens_the_smtp_panel_and_hides_the_graph_panel(self):
        self.make_graph()
        self.use_provider("smtp")

        response = self.client.get(self.edit_url)

        self.assertTrue(response.context["smtp_enabled"])
        self.assertFalse(response.context["graph_enabled"])
        self.assertNotIn("hidden", self.panel_attrs(response, "smtp-provider-settings"))
        self.assertIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertNotContains(response, "existing-secret")

    def test_graph_panel_shows_stored_values_and_no_credential_input(self):
        self.make_graph()
        self.use_provider("graph")

        response = self.client.get(self.edit_url)

        for value in (TENANT_ID, CLIENT_ID, "mailer@example.com"):
            self.assertContains(response, f'value="{value}"')
        for name in CREDENTIAL_INPUTS:
            self.assertNotContains(response, f'name="{name}"')
        self.assertContains(response, "installed on the Graph config's own page")
        self.assert_no_key_material(response.content)

    def test_graph_inputs_carry_the_markers_the_provider_toggle_script_reads(self):
        self.use_provider("graph")

        response = self.client.get(self.edit_url)

        fields = response.context["graph_form"].fields
        self.assertEqual(fields["tenant_id"].widget.attrs["data-graph-required"], "true")
        self.assertEqual(fields["mailbox"].widget.attrs["data-graph-required"], "false")
        self.assertEqual(tuple(fields), GRAPH_FIELDS)
        self.assertContains(response, 'graph: document.getElementById("graph-provider-settings")')
        self.assertContains(response, 'smtp: document.getElementById("smtp-provider-settings")')


class SelectingGraphTests(GraphSettingsTestCase):
    def test_a_new_graph_config_cannot_be_activated_here_without_a_mailbox_scope(self):
        # The scope is a list of mailboxes, edited on the Graph config's own admin page; this page links there.
        response = self.client.post(self.edit_url, self.post_data("graph"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["email_form"].errors["provider"], [PROVIDER_ERROR])
        self.assertContains(response, "Edit the mailbox scope and permission levels")
        self.assertContains(response, reverse("admin:core_microsoftgraphproviderconfig_add"))
        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())
        self.config.refresh_from_db()
        self.assertNotEqual(self.config.provider, "graph")

    def test_selecting_graph_activates_the_provider_with_a_scoped_graph_config(self):
        self.make_graph()

        response = self.client.post(self.edit_url, self.post_data("graph"))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        graph = MicrosoftGraphProviderConfig.objects.get()
        self.assertTrue(graph.is_active)
        self.assertEqual((graph.name, graph.tenant_id, graph.client_id), ("Outlook Sender", TENANT_ID, CLIENT_ID))
        self.assertEqual((graph.mailbox, graph.messages_per_minute), ("mailer@example.com", 20))
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "graph")
        self.assertEqual(self.config.from_email, "updated@example.com")
        self.assertTrue(self.config.delivery_configured)
        self.assertEqual(EmailServiceConfig.objects.count(), 1)

    def test_saving_reports_success_and_the_summary_names_the_graph_mailbox(self):
        self.make_graph()
        response = self.client.post(self.edit_url, self.post_data("graph"), follow=True)

        self.assertContains(response, "Notification delivery settings saved.")
        self.assert_chip(response, "Microsoft Graph (mailer@example.com)", "success")

    def test_selecting_graph_updates_the_existing_graph_config_in_place(self):
        graph = self.make_graph(name="Old name", mailbox="old@example.com", messages_per_minute=10)

        response = self.client.post(self.edit_url, self.post_data("graph", messages_per_minute="15"))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.assertEqual(MicrosoftGraphProviderConfig.objects.count(), 1)
        graph.refresh_from_db()
        self.assertEqual(
            (graph.name, graph.mailbox, graph.messages_per_minute), ("Outlook Sender", "mailer@example.com", 15)
        )

    def test_credential_inputs_posted_here_are_ignored(self):
        graph = self.make_graph()
        certificate = graph.current_certificate
        smuggled = {name.removeprefix("graph-"): "ignored-not-a-credential" for name in CREDENTIAL_INPUTS}

        response = self.client.post(self.edit_url, self.post_data("graph", messages_per_minute="12", **smuggled))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        graph.refresh_from_db()
        self.assertEqual(graph.messages_per_minute, 12)
        self.assertEqual(graph.current_certificate, certificate)
        self.assertEqual(snapshot(certificate)["store_version_id"], certificate.store_version_id)

    def test_changing_the_application_under_the_installed_certificate_is_rejected_and_changes_nothing(self):
        self.make_graph()
        before = self.state()

        response = self.client.post(
            self.edit_url, self.post_data("graph", client_id="bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("client_id", response.context["graph_form"].errors)
        self.assertContains(response, "Remove the installed certificates before changing the Entra application")
        self.assertEqual(self.state(), before)

    def test_messages_per_minute_accepts_the_documented_limits(self):
        self.make_graph()
        for limit in ("1", "30"):
            with self.subTest(limit=limit):
                response = self.client.post(self.edit_url, self.post_data("graph", messages_per_minute=limit))

                self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
                self.assertEqual(MicrosoftGraphProviderConfig.objects.get().messages_per_minute, int(limit))

    def test_verified_domain_tenant_and_object_id_mailbox_are_accepted(self):
        # The certificate was tested for this tenant; changing the tenant itself is refused (see above).
        self.make_graph(tenant_id="contoso.onmicrosoft.com")
        data = self.post_data("graph", tenant_id="contoso.onmicrosoft.com", mailbox=OBJECT_ID)

        response = self.client.post(self.edit_url, data)

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        graph = MicrosoftGraphProviderConfig.objects.get()
        self.assertEqual((graph.tenant_id, graph.mailbox), ("contoso.onmicrosoft.com", OBJECT_ID))

    def test_graph_without_a_mailbox_is_accepted_and_the_summary_falls_back_to_the_from_email(self):
        self.make_graph()
        response = self.client.post(self.edit_url, self.post_data("graph", mailbox=""), follow=True)

        self.assertEqual(MicrosoftGraphProviderConfig.objects.get().mailbox, "")
        self.assert_chip(response, "Microsoft Graph (updated@example.com)", "success")

    def test_selecting_graph_retains_the_aws_credentials_used_for_sms(self):
        before = snapshot(self.aws_config)

        self.client.post(self.edit_url, self.post_data("graph"))

        after = snapshot(self.aws_config)
        for row in (before, after):
            row.pop("updated_at")
        self.assertEqual(after, before)
        self.assertTrue(AWSCredentialConfig.load().sns_configured)


class SwitchingProvidersTests(GraphSettingsTestCase):
    def test_switching_from_graph_to_ses_needs_no_graph_fields_and_leaves_the_graph_row_untouched(self):
        graph = self.make_graph()
        self.use_provider("graph")
        before = snapshot(graph)

        response = self.client.post(self.edit_url, self.post_data("ses"))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")
        self.assertEqual(snapshot(graph), before)

    def test_graph_inputs_submitted_for_another_provider_are_ignored(self):
        graph = self.make_graph()
        before = snapshot(graph)
        data = self.post_data("ses")
        data.update(
            {
                "graph-tenant_id": "not a tenant!",
                "graph-client_id": "not-a-guid",
                "graph-mailbox": "not-an-email",
                "graph-messages_per_minute": "999",
            }
        )

        response = self.client.post(self.edit_url, data)

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.assertEqual(snapshot(graph), before)

    def test_round_trip_through_every_provider_keeps_the_graph_credentials(self):
        graph = self.make_graph()
        for provider in ("graph", "ses", "smtp", "graph"):
            with self.subTest(provider=provider):
                response = self.client.post(self.edit_url, self.post_data(provider))

                self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
                self.config.refresh_from_db()
                graph.refresh_from_db()
                self.assertEqual(self.config.provider, provider)
                self.assertEqual((graph.tenant_id, graph.client_id), (TENANT_ID, CLIENT_ID))
                self.assertTrue(graph.credential_configured)
                self.assertTrue(graph.is_active)

    def test_selecting_smtp_still_saves_the_smtp_config_and_leaves_the_graph_row_untouched(self):
        graph = self.make_graph()
        before = snapshot(graph)

        response = self.client.post(self.edit_url, self.post_data("smtp"))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.config.refresh_from_db()
        self.smtp_config.refresh_from_db()
        self.assertEqual(self.config.provider, "smtp")
        self.assertEqual((self.smtp_config.name, self.smtp_config.host), ("Updated SMTP", "mail.example.com"))
        self.assertEqual(self.smtp_config.password, "existing-secret")
        self.assertEqual(snapshot(graph), before)


class RejectedGraphInputTests(GraphSettingsTestCase):
    INVALID_INPUT = (
        ("tenant_id", "common", "Use the tenant GUID or a verified domain"),
        ("tenant_id", "not a tenant!", "Use the tenant GUID or a verified domain"),
        ("client_id", "not-a-guid", "The application (client) ID must be a GUID."),
        ("mailbox", "not-an-email", "Enter the mailbox email address"),
        ("messages_per_minute", "0", ""),
        ("messages_per_minute", "31", ""),
        ("messages_per_minute", "many", ""),
    )

    def test_invalid_graph_input_shows_field_errors_and_rolls_everything_back(self):
        before = self.state()

        for field, value, message in self.INVALID_INPUT:
            with self.subTest(field=field, value=value):
                response = self.client.post(self.edit_url, self.post_data("graph", **{field: value}))

                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["graph_form"].errors)
                if message:
                    self.assertContains(response, message)
                self.assertTrue(response.context["graph_enabled"])
                self.assertNotIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
                self.assertEqual(self.state(), before)
        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())

    def test_rejected_page_carries_no_key_material(self):
        self.make_graph()

        response = self.client.post(self.edit_url, self.post_data("graph", mailbox="not-an-email"))

        self.assertEqual(response.status_code, 200)
        self.assert_no_key_material(response.content)

    def test_selecting_graph_without_an_active_graph_config_is_rejected_on_the_provider_field(self):
        before = self.state()

        response = self.client.post(self.edit_url, self.post_data("graph", is_active=None))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["email_form"].errors["provider"], [PROVIDER_ERROR])
        self.assertContains(response, PROVIDER_ERROR)
        self.assertEqual(self.state(), before)
        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())

    def test_deactivating_the_only_graph_config_while_selecting_graph_changes_nothing(self):
        self.make_graph()
        before = self.state()

        response = self.client.post(self.edit_url, self.post_data("graph", is_active=None, name="Renamed"))

        self.assertEqual(response.context["email_form"].errors["provider"], [PROVIDER_ERROR])
        self.assertEqual(self.state(), before)
        self.assertTrue(MicrosoftGraphProviderConfig.load().is_configured)

    def test_activating_graph_without_an_installed_certificate_is_rejected_on_the_provider_field(self):
        self.make_graph(certificate=False)
        before = self.state()

        response = self.client.post(self.edit_url, self.post_data("graph"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["email_form"].errors["provider"], [PROVIDER_ERROR])
        self.assertEqual(self.state(), before)


class AccessControlTests(GraphSettingsTestCase):
    def test_staff_without_mail_access_cannot_read_or_change_the_graph_settings(self):
        self.make_graph()
        self.client.force_login(make_admin(apps=["event"], email="outsider@example.com"))
        before = self.state()

        self.assertEqual(self.client.get(self.edit_url).status_code, 403)
        self.assertEqual(self.client.post(self.edit_url, self.post_data("graph")).status_code, 403)
        self.assertEqual(self.client.get(self.summary_url).status_code, 403)
        self.assertEqual(self.state(), before)


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
    def test_graph_shows_its_ceiling_per_minute(self):
        self.make_graph(messages_per_minute=24)
        self.use_provider("graph")

        response = self.client.get(self.summary_url)

        self.assertContains(response, "Campaign Send Rate")
        self.assertContains(response, "24 emails/min")

    def test_ses_still_shows_the_cap_per_second(self):
        response = self.client.get(self.summary_url)

        self.assertContains(response, "12 emails/sec")


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
