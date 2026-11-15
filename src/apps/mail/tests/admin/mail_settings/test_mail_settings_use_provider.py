from unittest.mock import patch

from django.contrib.admin.models import CHANGE, LogEntry
from django.test import override_settings
from django.urls import reverse

from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.project.models.graph.test_graph_go_live_gate import DENY, evidence
from apps.event.tests.helpers import make_admin
from apps.mail.tests.admin.mail_settings.test_mail_settings_providers import (
    GRAPH_NOT_READY,
    SEND_TEST,
    EmailSendingMethodTestCase,
)


class UseProviderTests(EmailSendingMethodTestCase):
    def test_switching_to_a_ready_method_saves_it_and_records_who(self):
        response = self.client.post(self.use_url("smtp"))

        self.assertRedirects(response, self.settings_url, fetch_redirect_response=False)
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "smtp")
        self.assertEqual(self.messages(response), ["Email now sends through SMTP (was AWS SES)."])
        entry = LogEntry.objects.get(object_id=str(self.config.pk))
        self.assertEqual((entry.user_id, entry.action_flag), (self.superuser.pk, CHANGE))
        self.assertEqual(entry.get_change_message(), "Changed Provider.")

    def test_a_method_that_cannot_send_is_refused_and_nothing_changes(self):
        response = self.client.post(self.use_url("graph"))

        self.assertRedirects(response, self.settings_url, fetch_redirect_response=False)
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")
        self.assertEqual(self.messages(response), [f"Email cannot switch to Microsoft Graph: {GRAPH_NOT_READY}"])
        self.assertFalse(LogEntry.objects.exists())

    def test_choosing_the_method_in_use_changes_nothing(self):
        response = self.client.post(self.use_url("ses"))

        self.assertEqual(self.messages(response), ["Email already sends through AWS SES."])
        self.assertFalse(LogEntry.objects.exists())

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_microsoft_graph_needs_its_go_live_evidence(self):
        graph = create_graph_config(
            scope=("admin@example.com", "mailer@example.com"),
            name="Outlook",
            is_active=True,
            mailbox="mailer@example.com",
            access_check_deny_mailbox=DENY,
        )

        refused = self.client.post(self.use_url("graph"))
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")
        [message] = self.messages(refused)
        self.assertTrue(
            message.startswith(
                "Email cannot switch to Microsoft Graph: Email cannot switch to Microsoft Graph yet: no access check"
            )
        )

        evidence(graph)
        self.client.post(self.use_url("graph"))
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "graph")

    def test_the_switch_is_post_only_and_knows_only_the_four_methods(self):
        self.assertEqual(self.client.get(self.use_url("smtp")).status_code, 405)
        self.assertEqual(self.client.post(self.use_url("sendgrid")).status_code, 404)
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")

    def test_staff_without_the_mail_app_can_neither_switch_nor_test(self):
        self.client.force_login(make_admin(apps=["cms"], email="cms-only@example.com"))

        with patch(SEND_TEST) as send:
            self.assertEqual(self.client.post(self.use_url("smtp")).status_code, 403)
            self.assertEqual(self.client.get(self.page_url("smtp")).status_code, 403)
            self.assertEqual(self.client.post(self.page_url("smtp"), {"recipient": "ops@example.com"}).status_code, 403)

        send.assert_not_called()
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")


class TestEmailPerProviderTests(EmailSendingMethodTestCase):
    def test_a_method_not_in_use_is_tested_without_switching_to_it(self):
        with patch(SEND_TEST, return_value="SMTP") as send:
            response = self.client.post(self.page_url("smtp"), {"recipient": "ops@example.com"})

        self.assertRedirects(response, self.settings_url, fetch_redirect_response=False)
        sent_with = send.call_args.kwargs["config"]
        self.assertEqual(
            (sent_with.pk, sent_with.provider, sent_with.from_email), (self.config.pk, "smtp", "admin@example.com")
        )
        self.assertEqual(send.call_args.kwargs["recipient"], "ops@example.com")
        self.assertEqual(
            self.messages(response), ["Test email sent to ops@example.com via SMTP (config: Production Mail)."]
        )
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")

    def test_smtp_test_goes_through_the_smtp_server(self):
        with patch("apps.core.services.email.smtp.smtplib.SMTP") as smtp_class:
            smtp_class.return_value.send_message.return_value = {}  # no recipient refused
            response = self.client.post(self.page_url("smtp"), {"recipient": "ops@example.com"})

        self.assertEqual(
            self.messages(response), ["Test email sent to ops@example.com via SMTP (config: Production Mail)."]
        )
        smtp_class.assert_called_once()
        self.assertEqual(smtp_class.call_args.args[:2], ("smtp.example.com", 587))
        smtp_class.return_value.login.assert_called_once_with("mailer", "pw")
        self.assertEqual(smtp_class.return_value.send_message.call_args.kwargs["to_addrs"], ["ops@example.com"])

    def test_a_method_that_cannot_send_is_never_tried(self):
        page = self.client.get(self.page_url("graph"))
        self.assertEqual(page.context["send_problem"], GRAPH_NOT_READY)
        self.assertContains(page, "This method cannot send yet:")

        with patch(SEND_TEST) as send:
            response = self.client.post(self.page_url("graph"), {"recipient": "ops@example.com"})

        send.assert_not_called()
        self.assertEqual(
            self.messages(response), [f"Cannot send a test email through Microsoft Graph: {GRAPH_NOT_READY}"]
        )

    def test_the_test_page_offers_every_method(self):
        response = self.client.get(self.page_url("smtp"))

        self.assertContains(response, "Send Test Email via SMTP - Notification Delivery")
        links = {link["label"]: link for link in response.context["method_links"]}
        self.assertEqual(list(links), ["AWS SES", "SMTP", "Microsoft Graph", "Gmail API (Google Workspace)"])
        self.assertTrue(links["SMTP"]["selected"])
        self.assertTrue(links["AWS SES"]["in_use"])
        self.assertEqual(
            [label for label, link in links.items() if not link["ready"]],
            ["Microsoft Graph", "Gmail API (Google Workspace)"],
        )
        self.assertContains(response, "(in use)")

    def test_the_original_test_page_tests_the_method_in_use(self):
        with patch(SEND_TEST, return_value="AWS SES") as send:
            self.client.post(reverse("admin:mail_settings_test_email"), {"recipient": "ops@example.com"})

        self.assertEqual(send.call_args.kwargs["config"].provider, "ses")

    def test_the_recipient_must_be_an_email_address(self):
        with patch(SEND_TEST) as send:
            response = self.client.post(self.page_url("smtp"), {"recipient": "not-an-address"})

        send.assert_not_called()
        self.assertRedirects(response, self.page_url("smtp"), fetch_redirect_response=False)
        self.assertEqual(self.messages(response), ["Enter a valid recipient email address."])

    def test_an_unknown_method_is_not_found(self):
        self.assertEqual(self.client.get(self.page_url("sendgrid")).status_code, 404)
