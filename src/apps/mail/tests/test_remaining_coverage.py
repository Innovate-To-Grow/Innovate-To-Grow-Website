"""Coverage for scattered remaining lines: action methods, model cleans, widgets, admin badges."""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_event, make_superuser, make_ticket
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.admin.recipient_log import RecipientLogAdmin
from apps.mail.admin.sms_campaign import SmsCampaignAdmin
from apps.mail.models import EmailCampaign, RecipientLog, SmsCampaign
from apps.mail.models.campaign import EmailCampaign as CampaignModel
from apps.mail.models.recipient_log import RecipientLog as RecipientLogModel
from apps.mail.models.sms_campaign import SmsCampaign as SmsModel


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

    def test_delete_permission_requires_mail_app_access(self):
        from apps.authn.models import Member
        from apps.event.tests.helpers import make_admin, make_superuser

        def _req(user):
            request = self.factory.get("/")
            request.user = user
            return request

        mail_staff = make_admin(apps=["mail"], email="maillog-delete@example.com")
        other_staff = make_admin(apps=["cms"], email="cmslog-delete@example.com")
        superuser = make_superuser(email="su-maillog-delete@example.com")

        # Mail-granted staff and superuser may delete; other-app staff and
        # bare staff (no admin_apps) may not.
        self.assertTrue(self.admin.has_delete_permission(_req(mail_staff)))
        self.assertTrue(self.admin.has_delete_permission(_req(superuser)))
        self.assertFalse(self.admin.has_delete_permission(_req(other_staff)))
        self.assertFalse(self.admin.has_delete_permission(_req(Member(is_staff=True))))
        self.assertFalse(self.admin.has_delete_permission(_req(Member(is_staff=False))))


class ModelStrAndCleanTests(TestCase):
    def test_recipient_log_str(self):
        campaign = EmailCampaign.objects.create(subject="s", body="b")
        log = RecipientLogModel(campaign=campaign, email_address="x@example.com", status="delivered")
        self.assertIn("x@example.com", str(log))
        self.assertIn("Delivered", str(log))

    def test_email_campaign_clean_rejects_unsafe_redirect(self):
        campaign = CampaignModel(subject="s", body="b", login_redirect_path="//evil.com")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("login_redirect_path", ctx.exception.message_dict)

    def test_email_campaign_clean_requires_event_for_event_audience(self):
        campaign = CampaignModel(
            subject="s", body="b", login_redirect_path="/account", audience_type="event_registrants"
        )
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("event", ctx.exception.message_dict)

    def test_email_campaign_clean_requires_ticket_for_ticket_audience(self):
        event = make_event()
        campaign = CampaignModel(
            subject="s",
            body="b",
            login_redirect_path="/account",
            audience_type="ticket_type",
            event=event,
            manual_emails="",
        )
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("manual_emails", ctx.exception.message_dict)

    def test_email_campaign_clean_requires_manual_emails(self):
        campaign = CampaignModel(
            subject="s", body="b", login_redirect_path="/account", audience_type="manual", manual_emails=""
        )
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("manual_emails", ctx.exception.message_dict)

    def test_email_campaign_clean_requires_exclude_event(self):
        campaign = CampaignModel(
            subject="s",
            body="b",
            login_redirect_path="/account",
            audience_type="subscribers",
            exclude_audience_type="event_registrants",
        )
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("exclude_event", ctx.exception.message_dict)

    def test_sms_campaign_clean_requires_event(self):
        campaign = SmsModel(message="m", audience_type="event_registrants")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("event", ctx.exception.message_dict)

    def test_sms_campaign_clean_requires_ticket(self):
        event = make_event()
        campaign = SmsModel(message="m", audience_type="ticket_type", event=event, ticket_id="")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("ticket_id", ctx.exception.message_dict)

    def test_sms_campaign_clean_manual_requires_phones(self):
        campaign = SmsModel(message="m", audience_type="manual", manual_phones="")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("manual_phones", ctx.exception.message_dict)

    def test_sms_campaign_clean_manual_rejects_invalid_phone(self):
        campaign = SmsModel(message="m", audience_type="manual", manual_phones="12345")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("manual_phones", ctx.exception.message_dict)

    def test_sms_campaign_clean_manual_accepts_valid_phone(self):
        campaign = SmsModel(message="m", audience_type="manual", manual_phones="+12095551234")
        campaign.clean()  # should not raise

    def test_sms_campaign_clean_requires_exclude_event(self):
        campaign = SmsModel(message="m", audience_type="subscribers", exclude_audience_type="event_registrants")
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("exclude_event", ctx.exception.message_dict)

    def test_sms_campaign_clean_requires_exclude_ticket(self):
        event = make_event()
        campaign = SmsModel(
            message="m",
            audience_type="subscribers",
            exclude_audience_type="ticket_type",
            exclude_event=event,
            exclude_ticket_id="",
        )
        with self.assertRaises(ValidationError) as ctx:
            campaign.clean()
        self.assertIn("exclude_ticket_id", ctx.exception.message_dict)

    def test_sms_campaign_str_uses_message_fallback(self):
        campaign = SmsModel(name="", message="Hi there friends", status="draft")
        self.assertIn("Hi there friends", str(campaign))

    def test_sms_recipient_log_str(self):
        from apps.mail.models import SmsRecipientLog

        campaign = SmsCampaign.objects.create(name="A", message="m")
        log = SmsRecipientLog(campaign=campaign, phone_number="+12095551234", status="sent")
        self.assertEqual(str(log), "+12095551234 - Sent")


class TicketSelectWidgetTests(TestCase):
    def test_create_option_adds_data_event_attribute(self):
        from apps.event.models import Ticket
        from apps.mail.admin.campaign.widgets import ManualEmailsWidget, TicketSelectWidget

        event = make_event()
        ticket = make_ticket(event, name="VIP")
        widget = TicketSelectWidget()
        widget.choices = SimpleNamespace(queryset=Ticket.objects.filter(pk=ticket.pk))

        option = widget.create_option("ticket", str(ticket.pk), "VIP", False, 0)

        self.assertEqual(option["attrs"]["data-event"], str(event.pk))

        # An empty value yields no data-event attribute.
        empty_option = widget.create_option("ticket", "", "----", False, 1)
        self.assertNotIn("data-event", empty_option["attrs"])

        # ManualEmailsWidget merges custom attrs over defaults.
        manual = ManualEmailsWidget(attrs={"rows": 12})
        self.assertEqual(manual.attrs["rows"], 12)

    def test_get_event_map_handles_non_queryset_choices(self):
        from apps.mail.admin.campaign.widgets import TicketSelectWidget

        widget = TicketSelectWidget()
        widget.choices = [("", "----")]  # plain list, no .queryset

        self.assertEqual(widget._get_event_map(), {})
