"""Admin access to the mail app's custom admin views.

Every Admin may use every custom Mail admin URL; a signed-in member who is not an Admin is sent to the admin login
(``admin_view``) and refused by the view's own check too (``refusal.assert_refused_to_member``), before any
service runs or anything changes.
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.event.tests.helpers import make_admin
from apps.mail.models import SmsCampaign
from apps.mail.tests.admin.admin_access.refusal import assert_refused_to_member, make_member


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
    """Shared setup: a regular member and an Admin."""

    def setUp(self):
        cache.clear()
        self.member = make_member(email="member@example.com")
        self.admin_user = make_admin(email="admin@example.com")
        _make_delivery_configs()

    def tearDown(self):
        cache.clear()

    def assert_refused_to_member(self, url, method="get", **kwargs):
        return assert_refused_to_member(self, url, self.member, method, **kwargs)

    def assert_allowed_for_admin(self, url, method="get", **kwargs):
        self.client.force_login(self.admin_user)
        response = getattr(self.client, method)(url, **kwargs)
        self.assertNotEqual(response.status_code, 403, f"an Admin should reach {url} ({method})")
        self.assertFalse(response.get("Location", "").startswith(reverse("admin:login")), url)
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

    def test_preview_recipients_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_smscampaign_preview_recipients", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    def test_send_preview_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_smscampaign_send_preview", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    def test_send_confirm_get_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_smscampaign_send_confirm", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    def test_send_confirm_post_refused_to_members(self):
        # State-changing POST must be blocked before it can flip the campaign to "sending".
        url = reverse("admin:mail_smscampaign_send_confirm", args=[self.campaign.pk])
        self.assert_refused_to_member(url, method="post", data={"confirmation_text": self.campaign.name})
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "draft")

    def test_send_status_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_smscampaign_send_status", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    def test_send_status_json_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_smscampaign_send_status_json", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        response = self.assert_allowed_for_admin(url)
        self.assertEqual(response.status_code, 200)
