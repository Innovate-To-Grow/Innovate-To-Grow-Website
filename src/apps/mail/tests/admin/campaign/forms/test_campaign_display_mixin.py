from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_superuser
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.models import EmailCampaign
from apps.mail.services.campaign.preview import HTML_MARKER


class CampaignDisplayMixinTests(TestCase):
    def setUp(self):
        self.admin = EmailCampaignAdmin(EmailCampaign, AdminSite())
        self.factory = RequestFactory()

    def test_subject_preview_truncates(self):
        long_campaign = EmailCampaign(subject="s" * 80)
        self.assertEqual(self.admin.subject_preview(long_campaign), "s" * 60 + "...")

    def test_body_readonly_returns_dash_without_object(self):
        self.assertEqual(self.admin.body_readonly(None), "-")

    def test_body_readonly_escapes_and_embeds_base64(self):
        import base64

        campaign = EmailCampaign(subject="X", body="<b>Hi</b>")
        html = self.admin.body_readonly(campaign)

        self.assertIn("&lt;b&gt;Hi&lt;/b&gt;", html)
        self.assertIn(base64.b64encode(b"<b>Hi</b>").decode("ascii"), html)
        self.assertIn("Format: Plain text", html)
        self.assertIn("Copy text", html)

    def test_body_readonly_shows_and_copies_html_without_the_storage_marker(self):
        import base64

        marker = HTML_MARKER.strip()
        campaign = EmailCampaign(subject="X", body=f"{HTML_MARKER}{marker}\r\n<b>Hi</b>")
        html = self.admin.body_readonly(campaign)

        self.assertIn("Format: HTML", html)
        self.assertIn("Copy HTML", html)
        self.assertNotIn("raw-html", html)
        self.assertIn(base64.b64encode(b"<b>Hi</b>").decode("ascii"), html)

    def test_get_fieldsets_swaps_body_for_readonly_on_sent(self):
        campaign = EmailCampaign.objects.create(
            subject="Sent", body="Hi", login_redirect_path="/account", status="sent"
        )
        request = self.factory.get("/")

        fieldsets = self.admin.get_fieldsets(request, obj=campaign)
        all_fields = [f for _, opts in fieldsets for f in opts.get("fields", ())]

        self.assertIn("body_readonly", all_fields)
        self.assertNotIn("body", all_fields)

    def test_get_fieldsets_appends_error_details(self):
        campaign = EmailCampaign.objects.create(
            subject="Failed",
            body="Hi",
            login_redirect_path="/account",
            status="failed",
            error_message="boom",
        )
        request = self.factory.get("/")

        titles = [title for title, _ in self.admin.get_fieldsets(request, obj=campaign)]

        self.assertIn("Error Details", titles)

    def test_get_readonly_fields_includes_error_message(self):
        campaign = EmailCampaign.objects.create(
            subject="Failed",
            body="Hi",
            login_redirect_path="/account",
            status="failed",
            error_message="boom",
        )
        request = self.factory.get("/")

        readonly = self.admin.get_readonly_fields(request, obj=campaign)

        self.assertIn("error_message", readonly)
        self.assertIn("body_readonly", readonly)


class CampaignChangelistFallbackTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_changelist_uses_fallback_context_when_config_load_raises(self):
        with patch(
            "apps.core.models.EmailServiceConfig.load",
            side_effect=RuntimeError("config unavailable"),
        ):
            response = self.client.get(reverse("admin:mail_emailcampaign_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["email_config"])
        self.assertIsNone(response.context["aws_config"])
        self.assertIsNone(response.context["gmail_import_config"])
        self.assertEqual(response.context["gmail_mailbox"], "")
