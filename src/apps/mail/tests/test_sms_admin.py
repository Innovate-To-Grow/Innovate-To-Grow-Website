from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.core.models import AWSCredentialConfig
from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import SmsCampaign


def _add_phone(member, number, *, subscribe=True, verified=True):
    return ContactPhone.objects.create(
        member=member,
        phone_number=number,
        region="1-US",
        subscribe=subscribe,
        verified=verified,
    )


def _make_sms_config():
    AWSCredentialConfig.objects.all().delete()
    return AWSCredentialConfig.objects.create(
        name="AWS",
        is_active=True,
        access_key_id="aws-key",
        secret_access_key="aws-secret",
        default_region="us-west-2",
        sms_from_number="+12065550000",
    )


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class SmsCampaignAdminTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_sms_config()

    def test_sms_campaign_changelist_shows_delivery_configuration(self):
        response = self.client.get(reverse("admin:mail_smscampaign_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SMS Delivery Configuration")
        self.assertContains(response, "+12065550000")

    def test_sms_preview_page_shows_message_and_recipient_count(self):
        member = make_member(email="recipient@example.com", first_name="Recipient", last_name="User")
        _add_phone(member, "2095551001")
        campaign = SmsCampaign.objects.create(
            name="Preview SMS", message="Hi {{first_name}}", audience_type="all_members"
        )

        response = self.client.get(reverse("admin:mail_smscampaign_send_preview", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hi Hongzhe")
        self.assertContains(response, "Recipients:")
        self.assertContains(response, "1")

    def test_sms_recipient_preview_lists_phone_numbers(self):
        member = make_member(email="recipient@example.com", first_name="Recipient", last_name="User")
        _add_phone(member, "2095551001")
        campaign = SmsCampaign.objects.create(name="Recipients", message="Hi", audience_type="all_members")

        response = self.client.get(reverse("admin:mail_smscampaign_preview_recipients", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+12095551001")

    @patch("apps.mail.admin.sms_campaign.threading.Thread")
    def test_confirm_send_starts_background_sms_send(self, mock_thread):
        member = make_member(email="recipient@example.com")
        _add_phone(member, "2095551001")
        campaign = SmsCampaign.objects.create(name="Confirm SMS", message="Hi", audience_type="all_members")

        response = self.client.post(
            reverse("admin:mail_smscampaign_send_confirm", args=[campaign.pk]),
            {"confirmation_text": "Confirm SMS"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("status", response.url)
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    @patch("apps.mail.admin.sms_campaign.threading.Thread")
    @patch("apps.authn.services.email.send_email.senders.send_notification_email")
    def test_confirm_send_does_not_notify_staff(self, mock_notify, mock_thread):
        other_staff = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=other_staff,
            email_address="sms-staff-notify@example.com",
            email_type="primary",
            verified=True,
        )
        campaign = SmsCampaign.objects.create(
            name="No Staff Notify SMS",
            message="Hi",
            audience_type="manual",
            manual_phones="+12095551001",
        )

        response = self.client.post(
            reverse("admin:mail_smscampaign_send_confirm", args=[campaign.pk]),
            {"confirmation_text": "No Staff Notify SMS"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("status", response.url)
        mock_thread.assert_called_once()
        mock_notify.assert_not_called()

    @patch("apps.mail.admin.sms_campaign.threading.Thread")
    def test_wrong_confirmation_text_rejects_send(self, mock_thread):
        campaign = SmsCampaign.objects.create(
            name="Confirm SMS", message="Hi", audience_type="manual", manual_phones="+12095551001"
        )

        response = self.client.post(
            reverse("admin:mail_smscampaign_send_confirm", args=[campaign.pk]),
            {"confirmation_text": "Wrong"},
            follow=True,
        )

        self.assertContains(response, "Confirmation text does not match campaign name")
        mock_thread.assert_not_called()
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "draft")
