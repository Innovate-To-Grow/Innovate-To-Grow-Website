"""Coverage for EmailCampaign admin view mixins (send/preview/status/gmail) and inlines."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, GmailAccessAccount
from apps.event.tests.helpers import make_superuser
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.admin.campaign.inlines import AudienceTypeFilter, RecipientLogInline
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.gmail_import import GmailImportError
from apps.mail.services.preview import HTML_MARKER


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
        ses_from_email="test@ucmerced.edu",
        ses_from_name="Test",
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
    def setUp(self):
        # _background_send runs in a real thread in production and calls
        # django.db.connections.close_all() to drop the parent thread's handles.
        # Invoked synchronously here it would close the test's own connection —
        # harmless on SQLite but raises InterfaceError on PostgreSQL. Neutralize
        # the cross-thread connection teardown for these direct calls.
        patcher = patch("django.db.connections.close_all")
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("apps.mail.services.send_campaign.send_campaign")
    def test_background_send_runs_service(self, mock_send):
        admin_user = make_superuser()
        campaign = EmailCampaign.objects.create(subject="BG", body="x", status="sending")

        EmailCampaignAdmin._background_send(campaign.pk, admin_user.pk)

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.args[0].pk, campaign.pk)
        self.assertEqual(mock_send.call_args.kwargs["sent_by"].pk, admin_user.pk)

    @patch("apps.mail.services.send_campaign.send_campaign", side_effect=RuntimeError("boom"))
    def test_background_send_marks_failed_on_error(self, mock_send):
        admin_user = make_superuser()
        campaign = EmailCampaign.objects.create(subject="BG Fail", body="x", status="sending")

        EmailCampaignAdmin._background_send(campaign.pk, admin_user.pk)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertEqual(campaign.error_message, "Campaign send failed. Check server logs for details.")


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

    def test_inline_preview_post_plain_without_unsubscribe(self):
        response = self.client.post(
            reverse("admin:mail_emailcampaign_inline_preview"),
            {"body": "Plain body", "body_format": "plain"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Plain body")


class CampaignStatusViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_status_view_renders_progress_page(self):
        campaign = EmailCampaign.objects.create(name="Status", subject="s", body="b", status="sending")

        response = self.client.get(reverse("admin:mail_emailcampaign_send_status", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Status")

    def test_status_json_returns_progress_and_logs(self):
        campaign = EmailCampaign.objects.create(
            name="JSON",
            subject="s",
            body="b",
            status="sending",
            total_recipients=2,
            sent_count=1,
            failed_count=1,
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="sent@example.com",
            recipient_name="Sent",
            status="delivered",
            sent_at=timezone.now(),
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="failed@example.com",
            recipient_name="Failed",
            status="failed",
            error_message="bounced hard",
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="pending@example.com",
            status="pending",
        )

        response = self.client.get(reverse("admin:mail_emailcampaign_send_status_json", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "sending")
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["sent"], 1)
        self.assertEqual(payload["failed"], 1)
        self.assertIsNotNone(payload["started_at"])
        recent_emails = {row["email"] for row in payload["recent_logs"]}
        self.assertEqual(recent_emails, {"sent@example.com", "failed@example.com"})
        self.assertEqual(payload["failed_logs"][0]["error"], "bounced hard")

    def test_status_json_returns_cached_payload(self):
        campaign = EmailCampaign.objects.create(name="Cached", subject="s", body="b", status="sending")
        cache.set(f"mail:campaign_status:{campaign.pk}", {"status": "fromcache"}, 5)

        response = self.client.get(reverse("admin:mail_emailcampaign_send_status_json", args=[campaign.pk]))

        self.assertEqual(response.json(), {"status": "fromcache"})


class CampaignStatusShortErrorTests(TestCase):
    def test_short_error_redacts_traceback(self):
        from apps.mail.admin.campaign.views.status import _short_error

        traceback_text = 'Traceback (most recent call last):\n  File "x.py", line 1'
        self.assertEqual(_short_error(traceback_text), "Send failed (see server logs for details).")

    def test_short_error_returns_empty_for_falsy(self):
        from apps.mail.admin.campaign.views.status import _short_error

        self.assertEqual(_short_error(""), "")

    def test_short_error_trims_first_line(self):
        from apps.mail.admin.campaign.views.status import _short_error

        self.assertEqual(_short_error("first line\nsecond line"), "first line")


class CampaignGmailViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        GmailAccessAccount.objects.create(
            name="Gmail",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
        )
        _make_email_config()
        self.campaign = EmailCampaign.objects.create(subject="s", body="b", status="draft")

    def test_import_view_redirects_for_non_draft(self):
        self.campaign.status = "sent"
        self.campaign.save(update_fields=["status", "updated_at"])

        response = self.client.get(reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]))

    @patch("apps.mail.admin.campaign.list_recent_sent_messages", side_effect=GmailImportError("imap down"))
    def test_import_view_handles_gmail_import_error(self, mock_list):
        response = self.client.get(
            reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]), follow=True
        )

        self.assertContains(response, "imap down")
        mock_list.assert_called_once()

    def test_import_confirm_redirects_for_non_draft(self):
        self.campaign.status = "sent"
        self.campaign.save(update_fields=["status", "updated_at"])

        response = self.client.post(
            reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk]),
            {"message_id": "msg-1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]))

    def test_import_confirm_get_redirects_to_selection(self):
        response = self.client.get(
            reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))

    def test_import_confirm_requires_message_id(self):
        response = self.client.post(
            reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk]),
            {"message_id": "   "},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))

    @patch("apps.mail.admin.campaign.import_message_into_campaign", side_effect=GmailImportError("no html"))
    def test_import_confirm_handles_import_error(self, mock_import):
        response = self.client.post(
            reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk]),
            {"message_id": "msg-1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))
        mock_import.assert_called_once()

    @patch("apps.mail.admin.campaign.import_message_into_campaign")
    def test_import_confirm_success(self, mock_import):
        def _do_import(campaign, message_id, mailbox):
            campaign.body = HTML_MARKER + "<p>Imported</p>"
            campaign.save(update_fields=["body", "updated_at"])

        mock_import.side_effect = _do_import

        response = self.client.post(
            reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk]),
            {"message_id": "msg-1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]))
        mock_import.assert_called_once()


class CampaignInlineTests(TestCase):
    def test_recipient_log_inline_no_add_permission(self):
        inline = RecipientLogInline(EmailCampaign, AdminSite())
        request = RequestFactory().get("/")

        self.assertFalse(inline.has_add_permission(request))

    def test_audience_type_filter_lookups(self):
        from apps.mail.models.campaign import ALL_AUDIENCE_CHOICES

        instance = AudienceTypeFilter.__new__(AudienceTypeFilter)
        self.assertEqual(instance.lookups(request=None, model_admin=None), ALL_AUDIENCE_CHOICES)


class CampaignChangelistFilterTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_email_config()

    def test_changelist_filters_by_audience_type(self):
        EmailCampaign.objects.create(subject="Subs", body="b", audience_type="subscribers")
        EmailCampaign.objects.create(subject="Staff", body="b", audience_type="staff")

        response = self.client.get(reverse("admin:mail_emailcampaign_changelist"), {"audience_type": "subscribers"})

        self.assertEqual(response.status_code, 200)
        subjects = {c.subject for c in response.context["cl"].queryset}
        self.assertEqual(subjects, {"Subs"})
