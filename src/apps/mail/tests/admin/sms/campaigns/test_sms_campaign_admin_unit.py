from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from apps.mail.admin.sms_campaign import (
    SmsCampaignAdmin,
)
from apps.mail.models import SmsCampaign


class SmsCampaignAdminUnitTests(TestCase):
    """Direct-call coverage for display, fieldset, readonly, and status helpers."""

    def setUp(self):
        self.admin = SmsCampaignAdmin(SmsCampaign, AdminSite())
        self.factory = RequestFactory()

    def test_name_preview_truncates_long_names(self):
        long_campaign = SmsCampaign(name="x" * 80, message="Hi")
        short_campaign = SmsCampaign(name="Short", message="Hi")

        self.assertEqual(self.admin.name_preview(long_campaign), "x" * 60 + "...")
        self.assertEqual(self.admin.name_preview(short_campaign), "Short")

    def test_audience_badge_known_and_unknown(self):
        known = SmsCampaign(name="A", message="Hi", audience_type="subscribers")
        # An audience_type not present in the badge_colors map falls back to display+info.
        unknown = SmsCampaign(name="B", message="Hi", audience_type="unmapped_type")

        self.assertEqual(self.admin.audience_badge(known), ("Subscribers", "info"))
        display_value, color = self.admin.audience_badge(unknown)
        self.assertEqual(color, "info")
        self.assertEqual(display_value, unknown.get_audience_type_display())

    def test_phone_policy_badge(self):
        opt_in = SmsCampaign(name="A", message="Hi", phone_policy="verified_opt_in")
        any_verified = SmsCampaign(name="B", message="Hi", phone_policy="any_verified")

        self.assertEqual(self.admin.phone_policy_badge(opt_in), ("Verified opt-ins", "success"))
        self.assertEqual(self.admin.phone_policy_badge(any_verified), ("Any verified", "warning"))

    def test_status_badge_known_and_unknown(self):
        sending = SmsCampaign(name="A", message="Hi", status="sending")
        self.assertEqual(self.admin.status_badge(sending), ("Sending", "warning"))

    def test_message_readonly_returns_dash_when_no_object(self):
        self.assertEqual(self.admin.message_readonly(None), "-")

    def test_message_readonly_escapes_message(self):
        campaign = SmsCampaign(name="A", message="<script>alert(1)</script>")

        html = self.admin.message_readonly(campaign)

        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_get_fieldsets_swaps_message_for_readonly_on_sent_campaign(self):
        campaign = SmsCampaign.objects.create(name="Sent", message="Hi", status="sent")
        request = self.factory.get("/")

        fieldsets = self.admin.get_fieldsets(request, obj=campaign)

        all_fields = [field for _, opts in fieldsets for field in opts.get("fields", ())]
        self.assertIn("message_readonly", all_fields)
        self.assertNotIn("message", all_fields)

    def test_get_fieldsets_appends_error_section_when_error_present(self):
        campaign = SmsCampaign.objects.create(name="Failed", message="Hi", status="failed", error_message="boom")
        request = self.factory.get("/")

        fieldsets = self.admin.get_fieldsets(request, obj=campaign)

        titles = [title for title, _ in fieldsets]
        self.assertIn("Error Details", titles)

    def test_get_fieldsets_draft_keeps_editable_message(self):
        campaign = SmsCampaign.objects.create(name="Draft", message="Hi", status="draft")
        request = self.factory.get("/")

        fieldsets = self.admin.get_fieldsets(request, obj=campaign)

        all_fields = [field for _, opts in fieldsets for field in opts.get("fields", ())]
        self.assertIn("message", all_fields)
        self.assertNotIn("message_readonly", all_fields)

    def test_get_readonly_fields_for_sent_campaign_with_error(self):
        campaign = SmsCampaign.objects.create(name="Sent", message="Hi", status="sent", error_message="oops")
        request = self.factory.get("/")

        readonly = self.admin.get_readonly_fields(request, obj=campaign)

        self.assertIn("error_message", readonly)
        self.assertIn("message_readonly", readonly)
        self.assertIn("audience_type", readonly)

    def test_get_readonly_fields_draft_no_error_is_empty(self):
        campaign = SmsCampaign.objects.create(name="Draft", message="Hi", status="draft")
        request = self.factory.get("/")

        readonly = self.admin.get_readonly_fields(request, obj=campaign)

        self.assertNotIn("error_message", readonly)
        self.assertNotIn("message_readonly", readonly)
