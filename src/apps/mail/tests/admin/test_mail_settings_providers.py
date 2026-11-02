"""Broadcast Delivery → Email Sending Method: a card per provider, the switch, and a test email per provider."""

from unittest.mock import patch

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, SMTPProviderConfig
from apps.core.models.base.service_credentials.email import GMAIL_ACTIVATION_REQUIRED
from apps.core.tests.graph_helpers import create_graph_config
from apps.core.tests.models.test_graph_go_live_gate import DENY, evidence
from apps.event.tests.helpers import make_admin, make_superuser

SEND_TEST = "apps.mail.admin.settings.test_send._send_test_email"
GRAPH_NOT_READY = (
    "An active Microsoft Graph configuration whose mailbox scope lets the sender mailbox and the From address "
    "send is required before activation."
)


class EmailSendingMethodTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.superuser = make_superuser()
        self.client.force_login(self.superuser)
        self.config = EmailServiceConfig.objects.create(
            name="Production Mail", is_active=True, provider="ses", from_email="admin@example.com", from_name="I2G"
        )
        # A fixed SMS number, so the page never asks AWS for one.
        AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            sms_from_number="+12065550000",
        )
        SMTPProviderConfig.objects.create(
            name="Backup SMTP", is_active=True, host="smtp.example.com", port=587, username="mailer", password="pw"
        )
        patcher = patch("botocore.client.BaseClient._make_api_call", side_effect=AssertionError("no AWS calls"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings_url = reverse("admin:mail_sending_method")

    def use_url(self, provider):
        return reverse("admin:mail_settings_use_provider", args=[provider])

    def page_url(self, provider):
        return reverse("admin:mail_settings_test_email_provider", args=[provider])

    def messages(self, response):
        return [str(message) for message in get_messages(response.wsgi_request)]

    def cards(self):
        return {card["key"]: card for card in self.client.get(self.settings_url).context["provider_cards"]}


class ProviderCardTests(EmailSendingMethodTestCase):
    def test_every_method_has_a_card_saying_whether_it_can_send(self):
        response = self.client.get(self.settings_url)

        cards = response.context["provider_cards"]
        self.assertEqual([card["key"] for card in cards], ["ses", "smtp", "graph", "gmail"])
        by_key = {card["key"]: card for card in cards}
        self.assertTrue(by_key["ses"]["in_use"])
        self.assertEqual(by_key["ses"]["problem"], "")
        self.assertEqual(by_key["ses"]["detail"], "Region us-west-2")
        self.assertEqual((by_key["smtp"]["in_use"], by_key["smtp"]["problem"]), (False, ""))
        self.assertEqual(by_key["smtp"]["detail"], "smtp.example.com:587")
        self.assertEqual(by_key["graph"]["problem"], GRAPH_NOT_READY)
        self.assertEqual(by_key["gmail"]["problem"], GMAIL_ACTIVATION_REQUIRED)
        self.assertContains(response, "Email sending method")
        self.assertContains(response, 'id="email-method-graph"')
        self.assertContains(response, f'action="{self.use_url("smtp")}"')
        self.assertContains(response, f'href="{self.page_url("smtp")}"')
        # The method in use has no switch button, and one that cannot send has no test link.
        self.assertNotContains(response, f'action="{self.use_url("ses")}"')
        self.assertNotContains(response, f'href="{self.page_url("graph")}"')
        self.assertNotContains(response, f'action="{self.use_url("graph")}"')

    def test_a_method_in_use_that_cannot_send_says_so(self):
        AWSCredentialConfig.objects.all().delete()

        ses = self.cards()["ses"]

        self.assertTrue(ses["in_use"])
        self.assertEqual(ses["problem"], "Active AWS SES credentials are required before activation.")

    def test_configure_links_need_the_access_that_manages_each_method(self):
        superuser_cards = self.cards()
        self.client.force_login(make_admin(apps=["mail"], email="mail-only@example.com"))
        mail_staff_cards = self.cards()

        self.assertEqual(superuser_cards["smtp"]["configure_url"], reverse("admin:core_smtpproviderconfig_changelist"))
        self.assertEqual(
            superuser_cards["graph"]["configure_url"], reverse("admin:core_microsoftgraphproviderconfig_changelist")
        )
        self.assertEqual(
            superuser_cards["gmail"]["configure_url"], reverse("admin:core_gmailapiproviderconfig_changelist")
        )
        self.assertEqual(mail_staff_cards["ses"]["configure_url"], reverse("admin:mail_settings_edit"))
        self.assertEqual(mail_staff_cards["smtp"]["configure_url"], reverse("admin:mail_settings_edit"))
        self.assertEqual(mail_staff_cards["graph"]["configure_url"], "")
        self.assertEqual(mail_staff_cards["gmail"]["configure_url"], "")

    def test_without_a_saved_sender_config_every_method_asks_for_it_first(self):
        EmailServiceConfig.objects.all().delete()

        cards = self.cards()

        self.assertEqual(
            {card["problem"] for card in cards.values()},
            {"Save the Notification Delivery settings (sender name and From email) first."},
        )
        self.assertFalse(any(card["in_use"] for card in cards.values()))


class SendingMethodPageTests(EmailSendingMethodTestCase):
    def test_the_page_says_which_method_sends_all_email(self):
        response = self.client.get(self.settings_url)

        self.assertContains(response, "All site email is sent through")
        self.assertContains(
            response,
            '<div class="mt-1 text-base font-semibold text-font-important-light dark:text-font-important-dark" data-sending-method>AWS SES</div>',
            html=True,
        )
        self.assertContains(response, 'href="/admin/mail/settings/"')
        self.assertNotContains(response, 'id="tabs-items"')

    def test_with_email_switched_off_no_method_is_in_use(self):
        self.config.is_active = False
        self.config.save()

        response = self.client.get(self.settings_url)

        self.assertEqual(response.context["sending_method"], "None (email sending is off)")
        self.assertFalse(any(card["in_use"] for card in response.context["provider_cards"]))

    def test_notification_delivery_names_the_method_and_links_here(self):
        response = self.client.get(reverse("admin:mail_settings"))

        self.assertEqual(response.context["sending_method"], "AWS SES")
        self.assertContains(response, 'id="email-sending-method-summary"')
        self.assertContains(response, f'href="{self.settings_url}"')
        self.assertNotContains(response, 'id="email-sending-method"')

    def test_the_page_needs_the_mail_app(self):
        self.client.force_login(make_admin(apps=["cms"], email="cms-only@example.com"))

        self.assertEqual(self.client.get(self.settings_url).status_code, 403)


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
