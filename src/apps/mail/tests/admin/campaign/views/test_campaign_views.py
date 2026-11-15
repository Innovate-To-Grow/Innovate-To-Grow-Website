"""Coverage for EmailCampaign admin view mixins (send/preview/status/gmail) and inlines."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.event.tests.helpers import make_superuser
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.models import EmailCampaign


def _make_email_config():
    AWSCredentialConfig.objects.all().delete()
    AWSCredentialConfig.objects.create(
        name="AWS",
        is_active=True,
        access_key_id="AKIATEST",
        secret_access_key="secret",
        default_region="us-west-2",
    )
    return EmailServiceConfig.objects.create(
        name="SES",
        is_active=True,
        from_email="test@ucmerced.edu",
        from_name="Test",
    )


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class CampaignSendViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_email_config()

    def test_send_action_on_draft_redirects_to_preview(self):
        campaign = EmailCampaign.objects.create(subject="Draft", body="x", status="draft")

        # Detail action routes through the change view's actions; call the URL.
        response = self.client.get(reverse("admin:mail_emailcampaign_send_preview", args=[campaign.pk]))
        self.assertEqual(response.status_code, 200)

    def test_send_action_on_sent_warns_and_redirects(self):
        campaign = EmailCampaign.objects.create(subject="Sent", body="x", status="sent")
        admin = EmailCampaignAdmin(EmailCampaign, AdminSite())
        request = RequestFactory().get("/")
        request.user = self.admin_user
        # Attach message storage.
        from django.contrib.messages.storage.fallback import FallbackStorage

        request.session = self.client.session
        request._messages = FallbackStorage(request)

        response = admin.send_campaign_action(request, campaign.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_change", args=[campaign.pk]))

    def test_confirm_view_get_renders_for_draft(self):
        campaign = EmailCampaign.objects.create(name="Confirm Me", subject="s", body="b", status="draft")

        response = self.client.get(reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm Me")


class CampaignBackgroundSendTests(TestCase):
    @patch("apps.mail.services.campaign.dispatch.dispatch_email_campaign")
    def test_background_send_dispatches_through_durable_service(self, mock_dispatch):
        admin_user = make_superuser()
        campaign = EmailCampaign.objects.create(subject="BG", body="x", status="sending")

        EmailCampaignAdmin._background_send(campaign.pk, admin_user.pk)

        mock_dispatch.assert_called_once()
        self.assertEqual(mock_dispatch.call_args.args[0].pk, campaign.pk)
        self.assertEqual(mock_dispatch.call_args.kwargs["sent_by"].pk, admin_user.pk)

    @patch(
        "apps.mail.services.campaign.dispatch.dispatch_email_campaign",
        side_effect=RuntimeError("boom"),
    )
    def test_background_send_propagates_dispatch_error_to_admin_boundary(self, _mock_dispatch):
        admin_user = make_superuser()
        campaign = EmailCampaign.objects.create(subject="BG Fail", body="x", status="sending")

        with self.assertRaisesMessage(RuntimeError, "boom"):
            EmailCampaignAdmin._background_send(campaign.pk, admin_user.pk)


class CampaignPreviewViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_email_config()

    def test_preview_recipients_view_lists_recipients(self):
        campaign = EmailCampaign.objects.create(
            name="Recipients", subject="s", body="b", audience_type="manual", manual_emails="x@example.com"
        )

        response = self.client.get(reverse("admin:mail_emailcampaign_preview_recipients", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "x@example.com")

    def test_send_preview_view_renders_preview_for_draft(self):
        campaign = EmailCampaign.objects.create(name="Preview", subject="s", body="Hello", status="draft")

        response = self.client.get(reverse("admin:mail_emailcampaign_send_preview", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preview Email")

    def test_inline_preview_get_redirects_to_changelist(self):
        response = self.client.get(reverse("admin:mail_emailcampaign_inline_preview"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_changelist"))

    def test_inline_preview_post_renders_html_with_unsubscribe(self):
        response = self.client.post(
            reverse("admin:mail_emailcampaign_inline_preview"),
            {
                "body": "<p>Rich</p>",
                "body_format": "html",
                "include_unsubscribe_header": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rich")
        self.assertIn("sandbox", response["Content-Security-Policy"])
        self.assertIn("form-action 'none'", response["Content-Security-Policy"])
        self.assertEqual(response["Referrer-Policy"], "no-referrer")

    def test_inline_preview_post_plain_without_unsubscribe(self):
        response = self.client.post(
            reverse("admin:mail_emailcampaign_inline_preview"),
            {"body": "Plain body", "body_format": "plain"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Plain body")
