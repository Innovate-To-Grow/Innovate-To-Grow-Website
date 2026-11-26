"""Broadcast Delivery → Email Sending Method: a card per provider, the switch, and a test email per provider."""

from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, SMTPProviderConfig
from apps.core.models.base.service_credentials.email import GMAIL_ACTIVATION_REQUIRED
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.tests.admin.admin_access.refusal import assert_refused_to_member, make_member

SEND_TEST = "apps.mail.admin.settings.admin.test_send._send_test_email"
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

    def test_every_method_links_to_where_it_is_configured(self):
        self.client.force_login(make_admin(email="any-admin@example.com"))
        cards = self.cards()

        self.assertEqual(cards["ses"]["configure_url"], reverse("admin:mail_settings_edit"))
        self.assertEqual(cards["smtp"]["configure_url"], reverse("admin:core_smtpproviderconfig_changelist"))
        self.assertEqual(cards["graph"]["configure_url"], reverse("admin:core_microsoftgraphproviderconfig_changelist"))
        self.assertEqual(cards["gmail"]["configure_url"], reverse("admin:core_gmailapiproviderconfig_changelist"))

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

    def test_the_page_needs_an_admin(self):
        assert_refused_to_member(self, self.settings_url, make_member())
