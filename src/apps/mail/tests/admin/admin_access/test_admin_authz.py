"""Per-Django-app authorization gating for the mail app's custom admin views.

Custom admin URLs registered through ``admin_view(...)`` are gated only by
is_staff/is_active — Django does NOT run the per-app permission model for them.
The per-app model lives in ``apps.core.utils.access.user_can_access_app`` and the
``BaseModelAdmin`` permission methods. Without an explicit re-check, a staff
member whose ``Member.admin_apps`` lacks the ``mail`` app could still hit these
URLs and read data or trigger privileged sends.

These tests exercise the real Django admin through the test client:
  * a staff member WITHOUT the ``mail`` app gets HTTP 403 (the view's
    ``PermissionDenied`` is rendered as a 403 response by the test client), and
  * a superuser (who bypasses the per-app list) is allowed (not 403).
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import SmsCampaign


def _make_delivery_configs():
    AWSCredentialConfig.objects.all().delete()
    AWSCredentialConfig.objects.create(
        name="AWS",
        is_active=True,
        access_key_id="AKIATEST",
        secret_access_key="secret",
        default_region="us-west-2",
        sms_from_number="+12065550000",
    )
    EmailServiceConfig.objects.all().delete()
    return EmailServiceConfig.objects.create(
        name="SES",
        is_active=True,
        from_email="test@ucmerced.edu",
        from_name="Test",
    )


class MailAdminAuthzTestBase(TestCase):
    """Shared setup: a grant-less staff member and a superuser."""

    def setUp(self):
        cache.clear()
        # Staff member whose admin_apps does NOT include "mail".
        self.nogrant = make_admin(apps=["event"], email="nomail@example.com")
        self.superuser = make_superuser(email="master@example.com")
        _make_delivery_configs()

    def tearDown(self):
        cache.clear()

    def assert_denied_for_grantless(self, url, method="get", **kwargs):
        self.client.force_login(self.nogrant)
        response = getattr(self.client, method)(url, **kwargs)
        self.assertEqual(
            response.status_code,
            403,
            f"grant-less staff should be 403 on {url} ({method}), got {response.status_code}",
        )

    def assert_allowed_for_superuser(self, url, method="get", **kwargs):
        self.client.force_login(self.superuser)
        response = getattr(self.client, method)(url, **kwargs)
        self.assertNotEqual(
            response.status_code,
            403,
            f"superuser should not be 403 on {url} ({method}), got {response.status_code}",
        )
        return response


class SmsCampaignAdminAuthzTest(MailAdminAuthzTestBase):
    def setUp(self):
        super().setUp()
        self.campaign = SmsCampaign.objects.create(
            name="Blast",
            message="Hello {{ first_name }}",
            audience_type="manual",
            manual_phones="+12345678901",
            status="draft",
        )

    def test_preview_recipients_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_smscampaign_preview_recipients", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_preview_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_smscampaign_send_preview", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_confirm_get_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_smscampaign_send_confirm", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_confirm_post_denied_for_grantless(self):
        # State-changing POST must be blocked before it can flip the campaign to "sending".
        url = reverse("admin:mail_smscampaign_send_confirm", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url, method="post", data={"confirmation_text": self.campaign.name})
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "draft")

    def test_send_status_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_smscampaign_send_status", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_status_json_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_smscampaign_send_status_json", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        response = self.assert_allowed_for_superuser(url)
        self.assertEqual(response.status_code, 200)
