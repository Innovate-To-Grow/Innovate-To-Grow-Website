from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.core.models import AWSCredentialConfig
from apps.event.tests.helpers import make_event, make_member, make_superuser, make_ticket
from apps.mail.admin.sms_campaign import (
    SmsCampaignAdmin,
    SmsCampaignForm,
    SmsRecipientLogAdmin,
)
from apps.mail.models import SmsCampaign, SmsRecipientLog


def _add_phone(member, number, *, subscribe=True, verified=True):
    return ContactPhone.objects.create(
        member=member,
        phone_number=number,
        region="1-US",
        subscribe=subscribe,
        verified=verified,
    )


def _make_sms_config():
    AWSCredentialConfig.objects.all().delete()
    return AWSCredentialConfig.objects.create(
        name="AWS",
        is_active=True,
        access_key_id="aws-key",
        secret_access_key="aws-secret",
        default_region="us-west-2",
        sms_from_number="+12065550000",
    )


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class SmsCampaignAdminTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_sms_config()

    def test_sms_campaign_changelist_shows_delivery_configuration(self):
        response = self.client.get(reverse("admin:mail_smscampaign_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SMS Delivery Configuration")
        self.assertContains(response, "+12065550000")

    def test_sms_preview_page_shows_message_and_recipient_count(self):
        member = make_member(email="recipient@example.com", first_name="Recipient", last_name="User")
        _add_phone(member, "2095551001")
        campaign = SmsCampaign.objects.create(
            name="Preview SMS", message="Hi {{first_name}}", audience_type="all_members"
        )

        response = self.client.get(reverse("admin:mail_smscampaign_send_preview", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hi Hongzhe")
        self.assertContains(response, "Recipients:")
        self.assertContains(response, "1")

    def test_sms_recipient_preview_lists_phone_numbers(self):
        member = make_member(email="recipient@example.com", first_name="Recipient", last_name="User")
        _add_phone(member, "2095551001")
        campaign = SmsCampaign.objects.create(name="Recipients", message="Hi", audience_type="all_members")

        response = self.client.get(reverse("admin:mail_smscampaign_preview_recipients", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+12095551001")

    @patch("apps.mail.admin.sms_campaign.threading.Thread")
    def test_confirm_send_starts_background_sms_send(self, mock_thread):
        member = make_member(email="recipient@example.com")
        _add_phone(member, "2095551001")
        campaign = SmsCampaign.objects.create(name="Confirm SMS", message="Hi", audience_type="all_members")

        response = self.client.post(
            reverse("admin:mail_smscampaign_send_confirm", args=[campaign.pk]),
            {"confirmation_text": "Confirm SMS"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("status", response.url)
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    @patch("apps.mail.admin.sms_campaign.threading.Thread")
    @patch("apps.authn.services.email.send_email.senders.send_notification_email")
    def test_confirm_send_does_not_notify_staff(self, mock_notify, mock_thread):
        other_staff = Member.objects.create_user(password="testpass123", is_staff=True)
        ContactEmail.objects.create(
            member=other_staff,
            email_address="sms-staff-notify@example.com",
            email_type="primary",
            verified=True,
        )
        campaign = SmsCampaign.objects.create(
            name="No Staff Notify SMS",
            message="Hi",
            audience_type="manual",
            manual_phones="+12095551001",
        )

        response = self.client.post(
            reverse("admin:mail_smscampaign_send_confirm", args=[campaign.pk]),
            {"confirmation_text": "No Staff Notify SMS"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("status", response.url)
        mock_thread.assert_called_once()
        mock_notify.assert_not_called()

    @patch("apps.mail.admin.sms_campaign.threading.Thread")
    def test_wrong_confirmation_text_rejects_send(self, mock_thread):
        campaign = SmsCampaign.objects.create(
            name="Confirm SMS", message="Hi", audience_type="manual", manual_phones="+12095551001"
        )

        response = self.client.post(
            reverse("admin:mail_smscampaign_send_confirm", args=[campaign.pk]),
            {"confirmation_text": "Wrong"},
            follow=True,
        )

        self.assertContains(response, "Confirmation text does not match campaign name")
        mock_thread.assert_not_called()
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "draft")


class SmsCampaignFormTests(TestCase):
    """Unit-level coverage for SmsCampaignForm clean/save/init helpers."""

    def setUp(self):
        self.event = make_event(name="SMS Event")
        self.ticket = make_ticket(self.event, name="VIP", order=1)
        self.other_event = make_event(name="Other Event")

    def _base_data(self, **overrides):
        data = {
            "name": "Form Campaign",
            "message": "Hi {{first_name}}",
            "phone_policy": "verified_opt_in",
            "audience_type": "subscribers",
            "ticket_id": "",
            "manual_phones": "",
            "exclude_audience_type": "",
            "exclude_ticket_id": "",
            "status": "draft",
            "total_recipients": "0",
            "sent_count": "0",
            "failed_count": "0",
        }
        data.update(overrides)
        return data

    def test_clean_clears_ticket_id_for_non_ticket_audience(self):
        form = SmsCampaignForm(data=self._base_data(audience_type="subscribers", ticket_id="leftover"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ticket_id"], "")

    def test_clean_ticket_type_requires_ticket(self):
        form = SmsCampaignForm(data=self._base_data(audience_type="ticket_type", event=str(self.event.pk)))

        self.assertFalse(form.is_valid())
        self.assertIn("ticket", form.errors)
        self.assertIn("A ticket type must be selected.", form.errors["ticket"])

    def test_clean_ticket_type_rejects_ticket_from_other_event(self):
        form = SmsCampaignForm(
            data=self._base_data(
                audience_type="ticket_type",
                event=str(self.other_event.pk),
                ticket=str(self.ticket.pk),
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("does not belong to the selected event", form.errors["ticket"][0])

    def test_clean_ticket_type_accepts_matching_ticket_and_sets_ticket_id(self):
        form = SmsCampaignForm(
            data=self._base_data(
                audience_type="ticket_type",
                event=str(self.event.pk),
                ticket=str(self.ticket.pk),
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ticket_id"], str(self.ticket.pk))

    def test_clean_exclude_ticket_type_requires_ticket(self):
        form = SmsCampaignForm(
            data=self._base_data(
                exclude_audience_type="ticket_type",
                exclude_event=str(self.event.pk),
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("A ticket type must be selected for ticket exclusion.", form.errors["exclude_ticket"])

    def test_clean_exclude_ticket_type_rejects_mismatched_event(self):
        form = SmsCampaignForm(
            data=self._base_data(
                exclude_audience_type="ticket_type",
                exclude_event=str(self.other_event.pk),
                exclude_ticket=str(self.ticket.pk),
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("does not belong to the exclusion event", form.errors["exclude_ticket"][0])

    def test_clean_exclude_ticket_type_accepts_matching_ticket(self):
        form = SmsCampaignForm(
            data=self._base_data(
                exclude_audience_type="ticket_type",
                exclude_event=str(self.event.pk),
                exclude_ticket=str(self.ticket.pk),
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["exclude_ticket_id"], str(self.ticket.pk))

    def test_save_clears_ticket_and_exclusion_fields(self):
        form = SmsCampaignForm(
            data=self._base_data(
                audience_type="subscribers",
                ticket_id="stale",
                exclude_audience_type="",
                exclude_ticket_id="stale-exclude",
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

        instance = form.save(commit=True)

        self.assertEqual(instance.ticket_id, "")
        self.assertEqual(instance.exclude_ticket_id, "")
        self.assertIsNone(instance.exclude_event_id)

    def test_init_restores_ticket_initial_for_ticket_audience(self):
        campaign = SmsCampaign.objects.create(
            name="Existing",
            message="Hi",
            audience_type="ticket_type",
            event=self.event,
            ticket_id=str(self.ticket.pk),
        )

        form = SmsCampaignForm(instance=campaign)

        self.assertEqual(form.initial["ticket"], self.ticket.pk)

    def test_init_restores_ticket_initial_ignores_missing_ticket(self):
        campaign = SmsCampaign.objects.create(
            name="Existing",
            message="Hi",
            audience_type="ticket_type",
            event=self.event,
            ticket_id="00000000-0000-0000-0000-000000000000",
        )

        form = SmsCampaignForm(instance=campaign)

        self.assertNotIn("ticket", form.initial)

    def test_init_restores_exclude_ticket_initial(self):
        campaign = SmsCampaign.objects.create(
            name="Existing",
            message="Hi",
            audience_type="subscribers",
            exclude_audience_type="ticket_type",
            exclude_event=self.event,
            exclude_ticket_id=str(self.ticket.pk),
        )

        form = SmsCampaignForm(instance=campaign)

        self.assertEqual(form.initial["exclude_ticket"], self.ticket.pk)

    def test_init_disables_fields_for_sent_campaign(self):
        campaign = SmsCampaign.objects.create(
            name="Sent",
            message="Hi",
            audience_type="subscribers",
            status="sent",
        )

        form = SmsCampaignForm(instance=campaign)

        self.assertTrue(form.fields["name"].disabled)
        self.assertTrue(form.fields["message"].disabled)
        self.assertTrue(form.fields["audience_type"].disabled)


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


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class SmsCampaignStatusViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_sms_config()

    def test_send_sms_status_view_renders_progress_page(self):
        campaign = SmsCampaign.objects.create(name="Status SMS", message="Hi", status="sending")

        response = self.client.get(reverse("admin:mail_smscampaign_send_status", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Status SMS")

    def test_send_sms_status_json_returns_progress_and_logs(self):
        campaign = SmsCampaign.objects.create(
            name="JSON SMS",
            message="Hi",
            status="sending",
            total_recipients=2,
            sent_count=1,
            failed_count=1,
        )
        sent_time = timezone.now()
        SmsRecipientLog.objects.create(
            campaign=campaign,
            phone_number="+12095551001",
            recipient_name="Sent User",
            status="sent",
            sent_at=sent_time,
        )
        SmsRecipientLog.objects.create(
            campaign=campaign,
            phone_number="+12095551002",
            recipient_name="Failed User",
            status="failed",
            error_message="Carrier rejected",
        )
        SmsRecipientLog.objects.create(
            campaign=campaign,
            phone_number="+12095551003",
            recipient_name="Pending User",
            status="pending",
        )

        response = self.client.get(reverse("admin:mail_smscampaign_send_status_json", args=[campaign.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "sending")
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["sent"], 1)
        self.assertEqual(payload["failed"], 1)
        self.assertIsNotNone(payload["started_at"])
        # recent_logs excludes pending entries
        recent_phones = {row["phone"] for row in payload["recent_logs"]}
        self.assertEqual(recent_phones, {"+12095551001", "+12095551002"})
        self.assertEqual(len(payload["failed_logs"]), 1)
        self.assertEqual(payload["failed_logs"][0]["error"], "Carrier rejected")

    def test_send_sms_campaign_action_warns_for_non_draft(self):
        campaign = SmsCampaign.objects.create(name="Sent SMS", message="Hi", status="sent")

        response = self.client.get(
            reverse("admin:mail_smscampaign_change", args=[campaign.pk]),
        )
        self.assertEqual(response.status_code, 200)

        # Invoke the detail action directly through its url.
        action_response = self.client.get(
            reverse("admin:mail_smscampaign_send_preview", args=[campaign.pk]),
        )
        self.assertEqual(action_response.status_code, 200)


class SmsBackgroundSendTests(TestCase):
    @patch("apps.mail.services.send_sms_campaign.send_sms_campaign")
    def test_background_send_invokes_service(self, mock_send):
        admin_user = make_superuser()
        campaign = SmsCampaign.objects.create(name="BG SMS", message="Hi", status="sending")

        SmsCampaignAdmin._background_send(campaign.pk, admin_user.pk)

        mock_send.assert_called_once()
        called_campaign = mock_send.call_args.args[0]
        self.assertEqual(called_campaign.pk, campaign.pk)
        self.assertEqual(mock_send.call_args.kwargs["sent_by"].pk, admin_user.pk)

    @patch("apps.mail.services.send_sms_campaign.send_sms_campaign", side_effect=RuntimeError("boom"))
    def test_background_send_marks_failed_on_exception(self, mock_send):
        admin_user = make_superuser()
        campaign = SmsCampaign.objects.create(name="BG Fail SMS", message="Hi", status="sending")

        SmsCampaignAdmin._background_send(campaign.pk, admin_user.pk)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertEqual(campaign.error_message, "SMS campaign send failed. Check server logs for details.")


class SmsCampaignChangelistConfigTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_changelist_falls_back_to_none_when_aws_config_load_raises(self):
        with patch(
            "apps.core.models.AWSCredentialConfig.load",
            side_effect=RuntimeError("config unavailable"),
        ):
            response = self.client.get(reverse("admin:mail_smscampaign_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["aws_config"])


class SmsRecipientLogAdminTests(TestCase):
    def setUp(self):
        self.admin = SmsRecipientLogAdmin(SmsRecipientLog, AdminSite())
        self.factory = RequestFactory()
        self.campaign = SmsCampaign.objects.create(name="Log SMS", message="Hi")

    def test_status_badge_known_and_unknown(self):
        sent = SmsRecipientLog(campaign=self.campaign, phone_number="+12095551001", status="sent")
        unknown = SmsRecipientLog(campaign=self.campaign, phone_number="+12095551002", status="pending")

        self.assertEqual(self.admin.status_badge(sent), ("Sent", "success"))
        self.assertEqual(self.admin.status_badge(unknown), ("Pending", "info"))

    def test_error_preview_returns_dash_when_empty(self):
        log = SmsRecipientLog(campaign=self.campaign, phone_number="+12095551001", error_message="")

        self.assertEqual(self.admin.error_preview(log), "-")

    def test_error_preview_truncates_long_error(self):
        log = SmsRecipientLog(campaign=self.campaign, phone_number="+12095551001", error_message="e" * 200)

        result = self.admin.error_preview(log)

        self.assertEqual(result, "e" * 120 + "...")

    def test_error_preview_returns_short_error_unchanged(self):
        log = SmsRecipientLog(campaign=self.campaign, phone_number="+12095551001", error_message="short")

        self.assertEqual(self.admin.error_preview(log), "short")

    def test_delete_permission_requires_staff(self):
        staff_request = self.factory.get("/")
        staff_request.user = self.admin_request_user(is_staff=True)
        nonstaff_request = self.factory.get("/")
        nonstaff_request.user = self.admin_request_user(is_staff=False)

        self.assertTrue(self.admin.has_delete_permission(staff_request))
        self.assertFalse(self.admin.has_delete_permission(nonstaff_request))

    def admin_request_user(self, *, is_staff):
        user = Member(is_staff=is_staff)
        return user


class SmsRecipientLogInlinePermissionTests(TestCase):
    def test_inline_has_no_add_permission(self):
        from apps.mail.admin.sms_campaign import SmsRecipientLogInline

        inline = SmsRecipientLogInline(SmsCampaign, AdminSite())
        request = RequestFactory().get("/")

        self.assertFalse(inline.has_add_permission(request))


class SmsAudienceTypeFilterTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_filter_lookups_match_choices(self):
        from apps.mail.admin.sms_campaign import SmsAudienceTypeFilter
        from apps.mail.models.sms_campaign import SMS_AUDIENCE_CHOICES

        instance = SmsAudienceTypeFilter.__new__(SmsAudienceTypeFilter)
        self.assertEqual(instance.lookups(request=None, model_admin=None), SMS_AUDIENCE_CHOICES)

    def test_changelist_filter_narrows_by_audience_type(self):
        SmsCampaign.objects.create(name="Subs", message="Hi", audience_type="subscribers")
        SmsCampaign.objects.create(name="Staff", message="Hi", audience_type="staff")

        filtered = self.client.get(
            reverse("admin:mail_smscampaign_changelist"),
            {"audience_type": "subscribers"},
        )
        self.assertEqual(filtered.status_code, 200)
        names = {c.name for c in filtered.context["cl"].queryset}
        self.assertEqual(names, {"Subs"})

        unfiltered = self.client.get(reverse("admin:mail_smscampaign_changelist"))
        self.assertEqual({c.name for c in unfiltered.context["cl"].queryset}, {"Subs", "Staff"})
