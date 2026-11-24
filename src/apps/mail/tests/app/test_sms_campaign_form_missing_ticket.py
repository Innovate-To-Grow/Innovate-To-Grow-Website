from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from apps.event.tests.helpers import make_event
from apps.mail.admin.campaign.admin.recipient_log import RecipientLogAdmin
from apps.mail.models import EmailCampaign, RecipientLog, SmsCampaign


class SmsCampaignFormMissingTicketTests(TestCase):
    def test_restore_exclude_ticket_initial_ignores_missing_ticket(self):
        from apps.mail.admin.sms_campaign import SmsCampaignForm

        event = make_event()
        campaign = SmsCampaign.objects.create(
            name="A",
            message="m",
            audience_type="subscribers",
            exclude_audience_type="ticket_type",
            exclude_event=event,
            exclude_ticket_id="00000000-0000-0000-0000-000000000000",
        )

        form = SmsCampaignForm(instance=campaign)

        self.assertNotIn("exclude_ticket", form.initial)


class EmailRecipientLogAdminTests(TestCase):
    def setUp(self):
        self.admin = RecipientLogAdmin(RecipientLog, AdminSite())
        self.factory = RequestFactory()
        self.campaign = EmailCampaign.objects.create(subject="s", body="b")

    def _log(self, **kwargs):
        defaults = {"campaign": self.campaign, "email_address": "x@example.com"}
        defaults.update(kwargs)
        return RecipientLog(**defaults)

    def test_status_badge_maps_known_and_unknown(self):
        self.assertEqual(self.admin.status_badge(self._log(status="delivered")), ("Delivered", "success"))
        self.assertEqual(self.admin.status_badge(self._log(status="pending")), ("Pending", "info"))

    def test_bounce_badge_no_bounce(self):
        self.assertEqual(self.admin.bounce_badge(self._log(bounce_type="")), ("—", "info"))

    def test_bounce_badge_permanent_with_subtype(self):
        log = self._log(bounce_type="Permanent", bounce_subtype="General")
        self.assertEqual(self.admin.bounce_badge(log), ("Permanent/General", "danger"))

    def test_bounce_badge_transient_without_subtype(self):
        log = self._log(bounce_type="Transient", bounce_subtype="")
        self.assertEqual(self.admin.bounce_badge(log), ("Transient", "warning"))

    def test_error_preview_uses_diagnostic_for_bounce(self):
        log = self._log(status="bounced", error_message="", diagnostic_code="smtp; 550 blocked")
        self.assertEqual(self.admin.error_preview(log), "smtp; 550 blocked")

    def test_error_preview_uses_feedback_for_complaint(self):
        log = self._log(status="complained", error_message="", complaint_feedback_type="abuse")
        self.assertEqual(self.admin.error_preview(log), "abuse")

    def test_error_preview_complaint_defaults_when_no_feedback(self):
        log = self._log(status="complained", error_message="", complaint_feedback_type="")
        self.assertEqual(self.admin.error_preview(log), "complaint")

    def test_error_preview_returns_dash_when_empty(self):
        log = self._log(status="sent", error_message="")
        self.assertEqual(self.admin.error_preview(log), "-")

    def test_error_preview_truncates_long_message(self):
        log = self._log(status="failed", error_message="e" * 200)
        self.assertEqual(self.admin.error_preview(log), "e" * 120 + "...")

    def test_delete_permission_requires_an_admin(self):
        from apps.authn.models import Member
        from apps.event.tests.helpers import make_admin

        def _req(user):
            request = self.factory.get("/")
            request.user = user
            return request

        admin_user = make_admin(email="maillog-delete@example.com")

        # Every active Admin may delete; a regular member or an inactive staff account may not.
        self.assertTrue(self.admin.has_delete_permission(_req(admin_user)))
        self.assertTrue(self.admin.has_delete_permission(_req(Member(is_staff=True))))
        self.assertFalse(self.admin.has_delete_permission(_req(Member(is_staff=False))))
        self.assertFalse(self.admin.has_delete_permission(_req(Member(is_staff=True, is_active=False))))
