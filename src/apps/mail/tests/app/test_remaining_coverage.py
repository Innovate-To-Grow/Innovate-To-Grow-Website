"""Coverage for scattered remaining lines: action methods, model cleans, widgets, admin badges."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_superuser
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.admin.sms_campaign import SmsCampaignAdmin
from apps.mail.models import EmailCampaign, SmsCampaign


def _request_with_messages(factory, user):
    request = factory.get("/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class CampaignActionMethodTests(TestCase):
    def setUp(self):
        self.admin = EmailCampaignAdmin(EmailCampaign, AdminSite())
        self.factory = RequestFactory()
        self.user = make_superuser()

    def test_preview_email_action_redirects_to_preview(self):
        campaign = EmailCampaign.objects.create(subject="s", body="b")
        request = _request_with_messages(self.factory, self.user)

        response = self.admin.preview_email_action(request, campaign.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_send_preview", args=[campaign.pk]))

    def test_preview_recipients_action_redirects(self):
        campaign = EmailCampaign.objects.create(subject="s", body="b")
        request = _request_with_messages(self.factory, self.user)

        response = self.admin.preview_recipients_action(request, campaign.pk)

        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_preview_recipients", args=[campaign.pk]))

    def test_import_gmail_html_action_redirects(self):
        campaign = EmailCampaign.objects.create(subject="s", body="b")
        request = _request_with_messages(self.factory, self.user)

        response = self.admin.import_gmail_html_action(request, campaign.pk)

        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_import_gmail_html", args=[campaign.pk]))

    def test_send_campaign_action_draft_redirects_to_preview(self):
        campaign = EmailCampaign.objects.create(subject="s", body="b", status="draft")
        request = _request_with_messages(self.factory, self.user)

        response = self.admin.send_campaign_action(request, campaign.pk)

        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_send_preview", args=[campaign.pk]))

    def test_send_campaign_confirm_view_warns_for_non_draft(self):
        campaign = EmailCampaign.objects.create(subject="s", body="b", status="sent")
        request = _request_with_messages(self.factory, self.user)

        response = self.admin.send_campaign_confirm_view(request, campaign.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_change", args=[campaign.pk]))

    def test_send_campaign_confirm_view_warns_when_race_loses(self):
        campaign = EmailCampaign.objects.create(name="Race", subject="s", body="b", status="draft")
        request = self.factory.post(
            reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk]),
            {"confirmation_text": "Race"},
        )
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)

        # Another worker claimed the campaign first; the conditional UPDATE returns 0.
        with patch.object(EmailCampaign.objects, "filter") as mock_filter:
            mock_filter.return_value.update.return_value = 0
            with patch("django.conf.settings.ADMIN_REQUIRE_CONFIRMATION", False):
                response = self.admin.send_campaign_confirm_view(request, campaign.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_change", args=[campaign.pk]))

    def test_get_fieldsets_skips_options_without_fields(self):
        campaign = EmailCampaign.objects.create(subject="s", body="b", status="sent")
        request = _request_with_messages(self.factory, self.user)

        with patch.object(
            EmailCampaignAdmin.__mro__[-2],
            "get_fieldsets",
            return_value=[("Empty", {"classes": ("collapse",)})],
        ):
            fieldsets = self.admin.get_fieldsets(request, obj=campaign)

        # The fieldset without a "fields" key is preserved unchanged.
        self.assertIn(("Empty", {"classes": ("collapse",)}), fieldsets)


class SmsActionMethodTests(TestCase):
    def setUp(self):
        self.admin = SmsCampaignAdmin(SmsCampaign, AdminSite())
        self.factory = RequestFactory()
        self.user = make_superuser()

    def test_preview_sms_action_redirects_to_send_preview(self):
        campaign = SmsCampaign.objects.create(name="A", message="m")
        request = _request_with_messages(self.factory, self.user)

        response = self.admin.preview_sms_action(request, campaign.pk)

        self.assertEqual(response.url, reverse("admin:mail_smscampaign_send_preview", args=[campaign.pk]))

    def test_preview_recipients_action_redirects(self):
        campaign = SmsCampaign.objects.create(name="A", message="m")
        request = _request_with_messages(self.factory, self.user)

        response = self.admin.preview_recipients_action(request, campaign.pk)

        self.assertEqual(response.url, reverse("admin:mail_smscampaign_preview_recipients", args=[campaign.pk]))

    def test_send_sms_campaign_action_draft_redirects_to_preview(self):
        campaign = SmsCampaign.objects.create(name="A", message="m", status="draft")
        request = _request_with_messages(self.factory, self.user)

        response = self.admin.send_sms_campaign_action(request, campaign.pk)

        self.assertEqual(response.url, reverse("admin:mail_smscampaign_send_preview", args=[campaign.pk]))

    def test_send_sms_campaign_action_warns_for_non_draft(self):
        campaign = SmsCampaign.objects.create(name="A", message="m", status="sent")
        request = _request_with_messages(self.factory, self.user)

        response = self.admin.send_sms_campaign_action(request, campaign.pk)

        self.assertEqual(response.url, reverse("admin:mail_smscampaign_change", args=[campaign.pk]))

    def test_send_sms_confirm_view_warns_for_non_draft(self):
        campaign = SmsCampaign.objects.create(name="A", message="m", status="sent")
        request = _request_with_messages(self.factory, self.user)

        response = self.admin.send_sms_confirm_view(request, campaign.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_smscampaign_change", args=[campaign.pk]))

    def test_send_sms_confirm_view_warns_when_race_loses(self):
        campaign = SmsCampaign.objects.create(name="A", message="m", status="draft")
        factory = RequestFactory()
        request = factory.post(
            reverse("admin:mail_smscampaign_send_confirm", args=[campaign.pk]),
            {"confirmation_text": "A"},
        )
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)

        # Another worker flipped the status away from draft before the update runs.
        with patch.object(SmsCampaign.objects, "filter") as mock_filter:
            mock_filter.return_value.update.return_value = 0
            with patch("django.conf.settings.ADMIN_REQUIRE_CONFIRMATION", False):
                response = self.admin.send_sms_confirm_view(request, campaign.pk)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_smscampaign_change", args=[campaign.pk]))
