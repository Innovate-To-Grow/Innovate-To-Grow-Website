"""Broadcast Delivery → Email Sending Method: switching to Microsoft Graph when the From address is outside its scope.

Regression: email sent through AWS SES from the Google Workspace address while the Graph scope held only the Exchange
sender mailbox. "Use for email" kept the From address, so the Graph check refused the switch ("An active Microsoft
Graph configuration whose mailbox scope lets the sender mailbox and the From address send is required") although
Graph was configured and active. The switch now also moves the From address to the Graph sender mailbox.
"""

from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.test import override_settings

from apps.core.models import EmailServiceConfig, MicrosoftGraphMailboxScope
from apps.core.services.email.graph import GraphProvider
from apps.core.services.email.registry import resolve_provider
from apps.core.tests.graph_helpers import create_graph_config, grant
from apps.core.tests.models.test_graph_go_live_gate import DENY, evidence

from .test_mail_settings_providers import GRAPH_NOT_READY, SEND_TEST, EmailSendingMethodTestCase

FROM = "admin@example.com"  # the From address the sending config starts with (not in the Graph scope)
MAILBOX = "mailer@example.com"  # the Graph sender mailbox, in the scope
OBJECT_ID = "99999999-8888-7777-6666-555555555555"


class GraphFromAddressTests(EmailSendingMethodTestCase):
    def setUp(self):
        super().setUp()
        self.graph = create_graph_config(
            scope=(MAILBOX,), name="Outlook", is_active=True, mailbox=MAILBOX, access_check_deny_mailbox=DENY
        )

    def test_the_graph_card_is_ready_and_says_the_from_address_changes(self):
        response = self.client.get(self.settings_url)

        cards = {card["key"]: card for card in response.context["provider_cards"]}
        self.assertEqual((cards["graph"]["problem"], cards["graph"]["switch_from_email"]), ("", MAILBOX))
        self.assertEqual({cards[key]["switch_from_email"] for key in ("ses", "smtp", "gmail")}, {""})
        self.assertContains(response, f'action="{self.use_url("graph")}"')
        self.assertContains(response, f"Switching also changes the From address to {MAILBOX} (now {FROM})")
        self.assertContains(
            response, f'data-confirm="Send all site email through Microsoft Graph from {MAILBOX} from now on?"'
        )

    def test_use_for_email_switches_to_graph_and_its_sender_mailbox(self):
        response = self.client.post(self.use_url("graph"))

        self.assertRedirects(response, self.settings_url, fetch_redirect_response=False)
        self.config.refresh_from_db()
        self.assertEqual(
            (self.config.provider, self.config.from_email, self.config.from_name), ("graph", MAILBOX, "I2G")
        )
        self.assertTrue(self.config.is_active)
        self.assertEqual(
            self.messages(response),
            [f"Email now sends through Microsoft Graph (was AWS SES). The From address is now {MAILBOX} (was {FROM})."],
        )
        entry = LogEntry.objects.get(object_id=str(self.config.pk))
        self.assertEqual(entry.get_change_message(), "Changed Provider and From Email.")
        # What email now resolves to really sends through Graph, as and from the scoped mailbox.
        provider = resolve_provider(EmailServiceConfig.load())
        self.assertIsInstance(provider, GraphProvider)
        self.assertEqual((provider.mailbox, provider.from_email), (MAILBOX, MAILBOX))

    def test_a_from_address_graph_may_send_from_is_kept(self):
        grant(self.graph, FROM)

        self.assertEqual(self.cards()["graph"]["switch_from_email"], "")
        response = self.client.post(self.use_url("graph"))

        self.config.refresh_from_db()
        self.assertEqual((self.config.provider, self.config.from_email), ("graph", FROM))
        self.assertEqual(self.messages(response), ["Email now sends through Microsoft Graph (was AWS SES)."])
        self.assertEqual(LogEntry.objects.get().get_change_message(), "Changed Provider.")

    def test_without_a_sender_mailbox_that_is_an_email_address_graph_is_still_refused(self):
        grant(self.graph, OBJECT_ID)
        for mailbox in ("", OBJECT_ID):
            with self.subTest(mailbox=mailbox):
                self.graph.mailbox = mailbox
                self.graph.save()

                card = self.cards()["graph"]
                response = self.client.post(self.use_url("graph"))

                self.assertEqual((card["problem"], card["switch_from_email"]), (GRAPH_NOT_READY, ""))
                self.config.refresh_from_db()
                self.assertEqual((self.config.provider, self.config.from_email), ("ses", FROM))
                self.assertEqual(
                    self.messages(response), [f"Email cannot switch to Microsoft Graph: {GRAPH_NOT_READY}"]
                )
        self.assertFalse(LogEntry.objects.exists())

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_the_go_live_gate_still_applies_to_the_switch(self):
        refused = self.client.post(self.use_url("graph"))

        self.config.refresh_from_db()
        self.assertEqual((self.config.provider, self.config.from_email), ("ses", FROM))
        [message] = self.messages(refused)
        self.assertIn("Email cannot switch to Microsoft Graph yet: no access check", message)

        evidence(self.graph)
        self.client.post(self.use_url("graph"))

        self.config.refresh_from_db()
        self.assertEqual((self.config.provider, self.config.from_email), ("graph", MAILBOX))

    def test_the_graph_test_email_sends_from_the_address_switching_would_use(self):
        page = self.client.get(self.page_url("graph"))
        with patch(SEND_TEST, return_value="Microsoft Graph") as send:
            self.client.post(self.page_url("graph"), {"recipient": "ops@example.com"})

        self.assertContains(page, f"A test email will be sent from I2G &lt;{MAILBOX}&gt; through Microsoft Graph.")
        sent_with = send.call_args.kwargs["config"]
        self.assertEqual((sent_with.provider, sent_with.from_email), ("graph", MAILBOX))
        self.config.refresh_from_db()
        self.assertEqual((self.config.provider, self.config.from_email), ("ses", FROM))

    def test_graph_in_use_is_judged_with_the_from_address_it_sends_from(self):
        grant(self.graph, FROM)
        self.client.post(self.use_url("graph"))
        MicrosoftGraphMailboxScope.objects.filter(mailbox=FROM).delete()

        card = self.cards()["graph"]

        self.assertTrue(card["in_use"])
        self.assertEqual((card["problem"], card["switch_from_email"]), (GRAPH_NOT_READY, ""))
