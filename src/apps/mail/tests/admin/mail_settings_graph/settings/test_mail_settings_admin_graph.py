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

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, MicrosoftGraphProviderConfig, SMTPProviderConfig
from apps.core.services.email.graph import clear_access_token_cache
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import create_graph_config, private_key_lines
from apps.event.tests.helpers import make_superuser

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
    """An Admin, an active SES sender with AWS credentials (still needed for SMS) and a retained SMTP config."""

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
