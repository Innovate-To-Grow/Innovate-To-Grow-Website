"""Broadcast Delivery → Email Sending Method, end to end as production is set up for Microsoft Graph.

Email sends through AWS SES from an address outside the Graph scope, the Graph config is scoped to the Exchange
mailbox, the token claims what OIT granted (Mail.ReadWrite + Mail.Send), and the go-live gate is on. A superuser
runs the access check, then any Mail admin can send a test through Graph and switch email to it, with no exception
reference. Microsoft is faked at the transport, so every Graph request goes through the site's real code.
"""

import base64
import email
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from apps.core.admin.service_credentials.microsoft_graph_panel import ACCESS_CHECK_URL_NAME
from apps.core.models import EmailServiceConfig, MicrosoftGraphAccessCheck
from apps.core.services.email import EmailMessage, deliver_email
from apps.core.services.email.graph import auth, transport
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.services.graph_access.helpers import DENY, SCOPED, ProbeFake

from .test_mail_settings_providers import EmailSendingMethodTestCase

FROM = "admin@example.com"  # the From address email starts with (EmailSendingMethodTestCase), outside the scope


@override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
class GraphGoLiveAsInProductionTests(EmailSendingMethodTestCase):
    def setUp(self):
        super().setUp()
        auth.clear_access_token_cache()
        self.addCleanup(auth.clear_access_token_cache)
        self.microsoft = ProbeFake()  # its token claims Mail.ReadWrite + Mail.Send
        for name in ("post", "get"):
            patcher = patch.object(transport, name, new=getattr(self.microsoft, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.graph = create_graph_config(
            scope=(SCOPED,), name="Outlook", is_active=True, mailbox=SCOPED, access_check_deny_mailbox=DENY
        )

    def run_access_check(self):
        self.client.post(reverse(f"admin:{ACCESS_CHECK_URL_NAME}", args=[self.graph.pk]))
        return MicrosoftGraphAccessCheck.objects.get()

    def sent_messages(self):
        """(mailbox in the URL, parsed MIME message) of each MIME sendMail the site made."""
        return [
            (path.split("/")[3], email.message_from_bytes(base64.b64decode(body)))
            for method, _host, path, body, headers in self.microsoft.graph_calls()
            if method == "POST" and headers["Content-Type"] == "text/plain"
        ]

    def test_the_access_check_passes_cleanly_with_the_roles_oit_granted(self):
        check = self.run_access_check()

        self.assertEqual(check.granted_roles, ["Mail.ReadWrite", "Mail.Send"])
        self.assertIs(check.roles_within_approval, True)
        self.assertEqual({result["outcome"] for result in check.results}, {"PASS"})
        self.assertEqual(check.verdict, MicrosoftGraphAccessCheck.Verdict.COMPLIANT)
        self.assertEqual(self.graph.permission_exception_reference, "")

    def test_after_the_access_check_graph_can_be_tested_and_used_for_all_email(self):
        refused = self.cards()["graph"]
        self.assertIn("no access check is recorded", refused["problem"])
        self.run_access_check()
        probes = len(self.sent_messages())

        card = self.cards()["graph"]
        self.assertEqual((card["problem"], card["switch_from_email"]), ("", SCOPED))

        # Send test, before switching: through Graph, as and from the scoped mailbox.
        response = self.client.post(self.page_url("graph"), {"recipient": "ops@example.com"})
        self.assertEqual(
            self.messages(response),
            ["Test email sent to ops@example.com via Microsoft Graph (config: Production Mail)."],
        )
        [(mailbox, test_email)] = self.sent_messages()[probes:]
        self.assertEqual(mailbox, SCOPED)
        self.assertIn(SCOPED, test_email["From"])
        self.assertEqual(test_email["To"], "ops@example.com")

        # Use for email: every later email goes through Graph from the scoped mailbox.
        self.client.post(self.use_url("graph"))
        config = EmailServiceConfig.load()
        self.assertEqual((config.provider, config.from_email), ("graph", SCOPED))
        deliver_email(EmailMessage(subject="Sign-in code", to=("member@example.com",), text_body="123456"))
        mailbox, sign_in = self.sent_messages()[-1]
        self.assertEqual((mailbox, sign_in["Subject"], sign_in["To"]), (SCOPED, "Sign-in code", "member@example.com"))
        self.assertIn(SCOPED, sign_in["From"])
