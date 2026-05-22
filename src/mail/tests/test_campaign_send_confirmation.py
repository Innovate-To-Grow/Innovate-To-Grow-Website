"""Tests for the typed confirmation on the campaign send flow."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import EmailServiceConfig
from event.tests.helpers import make_superuser
from mail.models import EmailCampaign


def _make_campaign(name="Test Campaign", **kwargs):
    defaults = {
        "name": name,
        "subject": "Test Subject",
        "body": "Test body",
        "audience_type": "all_members",
        "status": "draft",
    }
    defaults.update(kwargs)
    return EmailCampaign.objects.create(**defaults)


def _make_email_config():
    return EmailServiceConfig.objects.create(
        name="Test SES",
        is_active=True,
        ses_access_key_id="AKIATEST",
        ses_secret_access_key="secret",
        ses_region="us-west-2",
        ses_from_email="test@ucmerced.edu",
        ses_from_name="Test",
    )


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class CampaignSendConfirmationTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_email_config()

    def test_confirm_page_shows_typed_input(self):
        campaign = _make_campaign(name="Input Visible Campaign")

        url = reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "confirm-input")
        self.assertContains(response, "Input Visible Campaign")
        self.assertContains(response, "confirm-send-btn")

    def test_post_without_confirmation_text_rejects(self):
        campaign = _make_campaign(name="No Text Campaign")

        url = reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk])
        response = self.client.post(url, {}, follow=True)

        self.assertContains(response, "Confirmation text does not match campaign name")
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "draft")

    def test_wrong_confirmation_text_rejects(self):
        campaign = _make_campaign(name="Right Name")

        url = reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk])
        response = self.client.post(url, {"confirmation_text": "Wrong Name"}, follow=True)

        self.assertContains(response, "Confirmation text does not match campaign name")
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "draft")

    @patch("mail.admin.campaign.views.send.CampaignSendMixin._background_send")
    def test_correct_confirmation_text_starts_send(self, mock_bg):
        campaign = _make_campaign(name="Correct Campaign")

        url = reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk])
        response = self.client.post(url, {"confirmation_text": "Correct Campaign"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("status", response.url)

    @patch("mail.admin.campaign.views.send.campaign_api.threading.Thread")
    def test_second_confirmation_post_does_not_start_duplicate_send(self, mock_thread):
        campaign = _make_campaign(name="Race Campaign")

        url = reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk])
        first_response = self.client.post(url, {"confirmation_text": "Race Campaign"})
        second_response = self.client.post(url, {"confirmation_text": "Race Campaign"}, follow=True)

        self.assertEqual(first_response.status_code, 302)
        self.assertContains(second_response, "already been sent")
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    @patch("mail.admin.campaign.views.send.CampaignSendMixin._background_send")
    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_notification_sent_after_campaign_send(self, mock_notify, mock_bg):
        from authn.models import ContactEmail, Member

        other_staff = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=other_staff, email_address="staff-notify@example.com", email_type="primary", verified=True
        )

        campaign = _make_campaign(name="Notify Campaign")

        url = reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk])
        self.client.post(url, {"confirmation_text": "Notify Campaign"})

        mock_notify.assert_called()
        call_kwargs = mock_notify.call_args[1]
        self.assertIn("Sent Campaign", call_kwargs["subject"])
        self.assertEqual(call_kwargs["recipient"], "staff-notify@example.com")

    @patch("mail.admin.campaign.views.send.CampaignSendMixin._background_send")
    @patch("authn.services.email.send_email.senders.send_notification_email")
    def test_notification_excludes_actor(self, mock_notify, mock_bg):
        campaign = _make_campaign(name="Exclude Actor Campaign")

        url = reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk])
        self.client.post(url, {"confirmation_text": "Exclude Actor Campaign"})

        for call in mock_notify.call_args_list:
            self.assertNotEqual(call[1]["recipient"], "admin@example.com")

    def test_already_sent_campaign_redirects(self):
        campaign = _make_campaign(name="Already Sent", status="sent")

        url = reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk])
        response = self.client.get(url, follow=True)

        self.assertContains(response, "already been sent")

    def test_submit_button_disabled_attribute_present(self):
        campaign = _make_campaign(name="Disabled Button")

        url = reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk])
        response = self.client.get(url)

        self.assertContains(response, "disabled")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class CampaignSendConfirmationDisabledTest(TestCase):
    """When ADMIN_REQUIRE_CONFIRMATION=False, send proceeds without typed input."""

    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_email_config()

    @patch("mail.admin.campaign.views.send.CampaignSendMixin._background_send")
    def test_post_without_text_succeeds_when_disabled(self, mock_bg):
        campaign = _make_campaign(name="No Confirm Needed")

        url = reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk])
        response = self.client.post(url, {})

        self.assertEqual(response.status_code, 302)
        self.assertIn("status", response.url)
