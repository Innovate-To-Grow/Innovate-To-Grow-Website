"""The Notification Delivery pages with the Gmail API provider: a read-only panel with no credential field, the
switch gated on the access-check evidence, and the summary line."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.models.base.service_credentials.email import GMAIL_ACTIVATION_REQUIRED
from apps.core.tests.gmail_api_helpers import CLIENT_ID, SERVICE_ACCOUNT, SUBJECT, make_config
from apps.event.tests.helpers import make_admin


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class GmailNotificationDeliveryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.email = EmailServiceConfig.objects.create(
            name="Mail", is_active=True, provider="ses", from_email=SUBJECT, from_name="I2G"
        )
        # A fixed SMS number, so the page never asks AWS for one.
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            sms_from_number="+12065550000",
        )
        patcher = patch("botocore.client.BaseClient._make_api_call", side_effect=AssertionError("no AWS calls"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.admin_user = make_admin(email="mail-admin@example.com")
        self.edit_url = reverse("admin:mail_settings_edit")

    def post(self, provider="gmail", **extra):
        data = {
            "email-name": "Mail",
            "email-is_active": "on",
            "email-provider": provider,
            "email-from_name": "I2G",
            "email-from_email": SUBJECT,
            "aws-name": "AWS",
            "aws-is_active": "on",
            "aws-access_key_id": "test-key",
            "aws-secret_access_key": "test-secret",
            "aws-default_region": "us-west-2",
            "aws-sms_message_template": "",
        }
        return self.client.post(self.edit_url, data | extra)

    def test_the_panel_is_read_only_and_links_to_the_config(self):
        config = make_config()
        self.client.force_login(self.admin_user)
        response = self.client.get(self.edit_url)
        self.assertContains(response, 'id="gmail-provider-settings"')
        self.assertContains(response, CLIENT_ID)
        self.assertContains(response, SERVICE_ACCOUNT)
        self.assertNotContains(response, "service_account_key")
        self.assertContains(response, reverse("admin:core_gmailapiproviderconfig_change", args=[config.pk]))
        self.assertNotContains(response, "needs the Core app")
        self.assertContains(response, '<option value="gmail"')

    def test_without_a_saved_config_it_links_to_adding_one(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(self.edit_url)
        self.assertContains(response, reverse("admin:core_gmailapiproviderconfig_add"))

    def test_switching_needs_the_access_check_evidence(self):
        config = make_config(checked=False)
        self.client.force_login(self.admin_user)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, escape(GMAIL_ACTIVATION_REQUIRED))
        self.email.refresh_from_db()
        self.assertEqual(self.email.provider, "ses")

        config.access_checked_at = timezone.now()
        config.save()
        self.assertEqual(self.post().status_code, 302)
        self.email.refresh_from_db()
        self.assertEqual(self.email.provider, "gmail")

    def test_an_admin_cannot_send_as_an_address_off_the_list(self):
        make_config()
        self.client.force_login(self.admin_user)
        response = self.post(**{"email-from_email": "dean@g.ucmerced.edu"})
        self.assertContains(response, escape(GMAIL_ACTIVATION_REQUIRED))

    def test_the_summary_names_the_gmail_api(self):
        make_config()
        EmailServiceConfig.objects.filter(pk=self.email.pk).update(provider="gmail")
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("admin:mail_settings"))
        self.assertContains(response, f"Gmail API ({SUBJECT})")
        self.assertContains(response, 'id="gmail-provider-summary"')
