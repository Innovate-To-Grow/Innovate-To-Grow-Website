"""Mail → SMS Settings, SMS Opt-outs, SMS Links and Ticket SMS in the admin, and what Broadcast SMS shows before a
send (estimate, opted-out recipients, links that are off, quiet hours). AWS is never called."""

from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactPhone
from apps.event.tests.helpers import make_admin, make_event, make_member, make_registration, make_superuser, make_ticket
from apps.mail.models import SmsCampaign, SmsConfig, SmsLinkToken, SmsOptOut, SmsRecipientLog, TicketSms
from apps.mail.services.sms import links
from apps.mail.services.sms.opt_out_sync import SyncResult

from ...services.sms.policy_helpers import QUIET_MOMENT, add_phone, at, opt_out, sms_aws_config, sms_settings

SYNC = "apps.mail.admin.sms_settings.opt_outs.sync_opt_outs"


def settings_form(**values):
    data = {
        "footer_enabled": "on",
        "footer_text": "Reply STOP to opt out.",
        "quiet_hours_enabled": "on",
        "quiet_hours_start": "20:00",
        "quiet_hours_end": "09:00",
        "quiet_hours_timezone": "America/Los_Angeles",
        "cost_per_segment": "0.0100",
        "ticket_sms_template": "Ticket: {{ticket_link}}",
        "ticket_link_validity_days": "7",
        "opt_out_sync_enabled": "on",
        "opt_out_list_name": "",
        "register_redirect_path": "/login",
    }
    data.update(values)
    return {key: value for key, value in data.items() if value is not None}


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False, FRONTEND_URL="https://i2g.example.edu")
class SmsSettingsAdminTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.change_url = reverse("admin:mail_smsconfig_change", args=[SmsConfig.load().pk])

    def test_the_list_opens_the_one_settings_page(self):
        response = self.client.get(reverse("admin:mail_smsconfig_changelist"))
        self.assertRedirects(response, self.change_url)
        self.assertEqual(self.client.get(reverse("admin:mail_smsconfig_add")).status_code, 403)

    def test_the_page_shows_the_short_link_its_qr_code_and_the_sync_state(self):
        response = self.client.get(self.change_url)
        self.assertContains(response, "https://i2g.example.edu/register")
        self.assertContains(response, reverse("admin:mail_smsconfig_register_qr", args=["svg"]))
        self.assertContains(response, "AWS opt-out sync")
        self.assertContains(response, "declares embedded links")
        self.assertNotContains(response, 'id="sms-opt-out-sync-now"')  # the button form lives on SMS Opt-outs only

    def test_quiet_hours_now_are_announced(self):
        with at(QUIET_MOMENT):
            response = self.client.get(self.change_url)
        self.assertContains(response, 'id="sms-quiet-hours-now"')

    def test_a_valid_save_is_stored(self):
        response = self.client.post(
            self.change_url,
            settings_form(links_enabled="on", quiet_hours_start="21:00", register_redirect_path="/account"),
        )
        self.assertEqual(response.status_code, 302, getattr(response, "context_data", {}).get("errors"))
        config = SmsConfig.load()
        self.assertTrue(config.links_enabled)
        self.assertEqual((config.quiet_hours_start, config.register_redirect_path), (time(21, 0), "/account"))

    def test_unsafe_or_inconsistent_settings_are_refused(self):
        cases = {
            "quiet_hours_timezone": settings_form(quiet_hours_timezone="Mars/Olympus"),
            "quiet_hours_end": settings_form(quiet_hours_end="20:00"),
            "footer_text": settings_form(footer_text="Thanks!"),
            "ticket_sms_template": settings_form(ticket_sms_template="No link here"),
            "ticket_sms_enabled": settings_form(ticket_sms_enabled="on"),
            "ticket_link_validity_days": settings_form(ticket_link_validity_days="30"),
            "register_redirect_path": settings_form(register_redirect_path="/register"),
        }
        for field, data in cases.items():
            with self.subTest(field=field):
                response = self.client.post(self.change_url, data)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context_data["adminform"].form.errors)

    def test_the_qr_code_is_shown_and_downloaded(self):
        url = reverse("admin:mail_smsconfig_register_qr", args=["svg"])
        shown = self.client.get(url)
        self.assertEqual((shown.status_code, shown["Content-Type"]), (200, "image/svg+xml"))
        self.assertTrue(shown["Content-Disposition"].startswith("inline"))
        self.assertIn(b"<svg", shown.content)
        png = self.client.get(reverse("admin:mail_smsconfig_register_qr", args=["png"]) + "?download=1")
        self.assertEqual(png["Content-Type"], "image/png")
        self.assertTrue(png["Content-Disposition"].startswith('attachment; filename="i2g-register-qr.png"'))
        self.assertTrue(png.content.startswith(b"\x89PNG"))
        self.assertEqual(self.client.get(reverse("admin:mail_smsconfig_register_qr", args=["gif"])).status_code, 404)

    @override_settings(FRONTEND_URL="")
    def test_without_a_public_address_there_is_no_qr_code(self):
        self.assertEqual(self.client.get(reverse("admin:mail_smsconfig_register_qr", args=["svg"])).status_code, 404)
        self.assertContains(self.client.get(self.change_url), "FRONTEND_URL is not set")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False, FRONTEND_URL="https://i2g.example.edu")
class PersonalLinksSwitchTests(TestCase):
    def test_only_the_i2g_master_can_turn_personal_links_on(self):
        make_admin(apps=["mail"], email="mail@example.com")
        self.client.login(username="mail@example.com", password="testpass123")
        change_url = reverse("admin:mail_smsconfig_change", args=[SmsConfig.load().pk])
        page = self.client.get(change_url)
        self.assertNotContains(page, 'name="personal_links_enabled"')
        response = self.client.post(change_url, settings_form(personal_links_enabled="on", links_enabled="on"))
        self.assertEqual(response.status_code, 302)
        config = SmsConfig.load()
        self.assertTrue(config.links_enabled)
        self.assertFalse(config.personal_links_enabled)

        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.assertContains(self.client.get(change_url), 'name="personal_links_enabled"')
        self.client.post(change_url, settings_form(personal_links_enabled="on", links_enabled="on"))
        self.assertTrue(SmsConfig.load().personal_links_enabled)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False, FRONTEND_URL="https://i2g.example.edu")
class SmsSettingsAccessTests(TestCase):
    def test_only_mail_staff_reach_the_settings_and_the_qr_code(self):
        make_admin(apps=["cms"], email="cms@example.com")
        self.client.login(username="cms@example.com", password="testpass123")
        self.assertEqual(self.client.get(reverse("admin:mail_smsconfig_register_qr", args=["svg"])).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:mail_smsconfig_changelist")).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:mail_smsoptout_sync")).status_code, 403)

        make_admin(apps=["mail"], email="mail@example.com")
        self.client.login(username="mail@example.com", password="testpass123")
        self.assertEqual(self.client.get(reverse("admin:mail_smsconfig_register_qr", args=["svg"])).status_code, 200)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SmsOptOutAdminTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.member = make_member(email="ada@example.com", first_name="Ada", last_name="Lovelace")
        self.phone = add_phone(self.member, "2095550101")

    def test_the_list_shows_each_number_its_members_and_the_sync(self):
        opt_out("+12095550101")
        response = self.client.get(reverse("admin:mail_smsoptout_changelist"))
        self.assertContains(response, "+12095550101")
        self.assertContains(response, "Ada Lovelace")
        self.assertContains(response, 'id="sms-opt-out-sync-now"')

    def test_staff_opt_a_number_out_and_its_phone_is_unsubscribed(self):
        response = self.client.post(
            reverse("admin:mail_smsoptout_add"), {"phone_number": "(209) 555-0101", "note": "Asked at the desk"}
        )
        self.assertEqual(response.status_code, 302)
        row = SmsOptOut.objects.get()
        self.assertEqual((row.phone_number, row.source, row.created_by), ("+12095550101", "staff", self.admin_user))
        self.phone.refresh_from_db()
        self.assertFalse(self.phone.subscribe)
        self.assertTrue(LogEntry.objects.filter(object_id=str(row.pk), action_flag=ADDITION).exists())

        again = self.client.post(reverse("admin:mail_smsoptout_add"), {"phone_number": "+12095550101", "note": ""})
        self.assertContains(again, "already opted out")
        bad = self.client.post(reverse("admin:mail_smsoptout_add"), {"phone_number": "12345", "note": ""})
        self.assertContains(bad, "Enter a US phone number")

    def test_a_number_that_opted_back_in_can_be_opted_out_again(self):
        row = opt_out("+12095550101", source="staff")
        SmsOptOut.objects.filter(pk=row.pk).update(cleared_at=row.opted_out_at)
        response = self.client.post(reverse("admin:mail_smsoptout_add"), {"phone_number": "+12095550101", "note": "x"})
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertTrue(row.is_active)
        self.assertEqual(SmsOptOut.objects.count(), 1)

    def test_the_list_filters_by_status(self):
        opt_out("+12095550101")
        opt_out("+12095550102", cleared_at=timezone.now())
        url = reverse("admin:mail_smsoptout_changelist")
        active = self.client.get(url, {"status": "active"})
        self.assertContains(active, "+12095550101")
        self.assertNotContains(active, "+12095550102")
        cleared = self.client.get(url, {"status": "cleared"})
        self.assertContains(cleared, "+12095550102")
        self.assertNotContains(cleared, "+12095550101")

    def test_a_row_is_read_only_and_never_deleted(self):
        row = opt_out("+12095550101")
        response = self.client.get(reverse("admin:mail_smsoptout_change", args=[row.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="_save"')
        self.assertEqual(self.client.get(reverse("admin:mail_smsoptout_delete", args=[row.pk])).status_code, 403)

    def test_lifting_ends_only_staff_opt_outs(self):
        staff_row = opt_out("+12095550101", source="staff")
        aws_row = opt_out("+12095550102")
        ContactPhone.objects.filter(pk=self.phone.pk).update(subscribe=False)  # as the staff opt-out left it
        response = self.client.post(
            reverse("admin:mail_smsoptout_changelist"),
            {"action": "lift_staff_opt_outs", "_selected_action": [str(staff_row.pk), str(aws_row.pk)]},
            follow=True,
        )
        self.assertContains(response, "Lifted 1 staff opt-out(s).")
        self.assertContains(response, "replies START")
        staff_row.refresh_from_db()
        aws_row.refresh_from_db()
        self.assertFalse(staff_row.is_active)
        self.assertTrue(aws_row.is_active)
        self.assertTrue(LogEntry.objects.filter(object_id=str(staff_row.pk), action_flag=CHANGE).exists())
        # Lifting never subscribes the phone again.
        self.assertFalse(ContactPhone.objects.get(pk=self.phone.pk).subscribe)

    @patch(SYNC, return_value=SyncResult("ok", listed=3, added=1, cleared=0))
    def test_sync_now_reads_aws_and_returns_to_a_page_of_this_site(self, sync):
        sync_url = reverse("admin:mail_smsoptout_sync")
        self.assertEqual(self.client.get(sync_url).status_code, 405)

        response = self.client.post(sync_url, {"next": "/admin/mail/smsconfig/"})
        self.assertEqual(response.url, "/admin/mail/smsconfig/")
        sync.assert_called_once_with()
        for unsafe in ("https://evil.example/admin/mail/", "//evil.example", "/admin/core/"):
            with self.subTest(unsafe=unsafe):
                self.assertEqual(
                    self.client.post(sync_url, {"next": unsafe}).url, reverse("admin:mail_smsoptout_changelist")
                )
        followed = self.client.post(sync_url, follow=True)
        self.assertContains(followed, "AWS opt-out sync: ok. Listed 3, added 1, cleared 0.")
        self.assertTrue(LogEntry.objects.filter(change_message__contains="Synced SMS opt-outs").exists())

    @patch(SYNC, return_value=SyncResult("failed", message="AWS refused to read the opted-out list. (AccessDenied)"))
    def test_a_failed_sync_is_reported_as_an_error(self, _sync):
        response = self.client.post(reverse("admin:mail_smsoptout_sync"), follow=True)
        self.assertContains(response, "AccessDenied")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False, FRONTEND_URL="https://i2g.example.edu")
class SmsRecordsAdminTests(TestCase):
    def setUp(self):
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_sms_links_are_listed_without_their_tokens_and_can_be_revoked(self):
        member = make_member(email="ada@example.com")
        add_phone(member, "2095550101")
        url = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=member, phone="+12095550101", redirect_path="/", validity_days=1
        )
        token = url.rsplit("/", 1)[1]
        response = self.client.get(reverse("admin:mail_smslinktoken_changelist"))
        self.assertContains(response, "Personal sign-in")
        self.assertNotContains(response, token)
        row = SmsLinkToken.objects.get()
        self.client.post(
            reverse("admin:mail_smslinktoken_changelist"),
            {"action": "revoke_selected_action", "_selected_action": [str(row.pk)]},
        )
        self.assertEqual(links.open_link(token).code, "expired")

    def test_a_links_status_follows_its_use_and_expiry(self):
        sms_settings(links_enabled=True, personal_links_enabled=True)
        member = make_member(email="ada@example.com")
        add_phone(member, "2095550101")
        used = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=member, phone="+12095550101", redirect_path="/", validity_days=1
        )
        links.open_link(used.rsplit("/", 1)[1])
        expired = SmsLinkToken.objects.create(
            token_hash="e" * 64, purpose="event", redirect_path="/", expires_at=timezone.now() - timedelta(days=1)
        )
        response = self.client.get(reverse("admin:mail_smslinktoken_changelist"))
        self.assertContains(response, "used")
        self.assertContains(response, "expired")
        self.assertContains(response, "Shared")
        self.assertTrue(expired.is_expired)

    def test_ticket_texts_are_listed_with_their_status(self):
        event = make_event()
        member = make_member(email="pho@example.com")
        registration = make_registration(member, event, make_ticket(event))
        TicketSms.objects.create(registration=registration, phone_number="+12095550101", status="opted_out")
        response = self.client.get(reverse("admin:mail_ticketsms_changelist"))
        self.assertContains(response, "+12095550101")
        self.assertContains(response, "Opted out")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True, FRONTEND_URL="https://i2g.example.edu")
class BroadcastSmsPolicyAdminTests(TestCase):
    def setUp(self):
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        sms_aws_config()
        for national, email in (("2095550101", "ada@example.com"), ("2095550102", "bo@example.com")):
            add_phone(make_member(email=email), national)

    def campaign(self, message="Hi {{first_name}}", **fields):
        return SmsCampaign.objects.create(name="Policy", message=message, audience_type="subscribers", **fields)

    def test_the_preview_shows_the_estimate_and_who_is_left_out(self):
        opt_out("+12095550102")
        response = self.client.get(reverse("admin:mail_smscampaign_send_preview", args=[self.campaign().pk]))
        self.assertContains(response, 'id="sms-estimate"')
        self.assertContains(response, "1 recipient skipped: opted out of texts.")
        self.assertContains(response, "Reply STOP to opt out.")
        self.assertContains(response, "Proceed to Send")

    def test_a_message_whose_links_are_off_cannot_go_on_to_send(self):
        campaign = self.campaign("Sign in: {{login_link}}")
        preview = self.client.get(reverse("admin:mail_smscampaign_send_preview", args=[campaign.pk]))
        self.assertContains(preview, 'id="sms-links-blocked-notice"')
        self.assertNotContains(preview, "Proceed to Send")
        confirm_url = reverse("admin:mail_smscampaign_send_confirm", args=[campaign.pk])
        self.assertNotContains(self.client.get(confirm_url), 'id="confirm-send-form"')
        response = self.client.post(confirm_url, {"confirmation_text": "Policy"}, follow=True)
        self.assertContains(response, "Links in SMS are turned off")
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "draft")

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    def test_quiet_hours_refuse_an_in_process_send_with_the_reason(self):
        campaign = self.campaign()
        with at(QUIET_MOMENT), patch("apps.mail.services.campaign.dispatch.launch.start_in_process_task") as start:
            confirm = self.client.get(reverse("admin:mail_smscampaign_send_confirm", args=[campaign.pk]))
            response = self.client.post(
                reverse("admin:mail_smscampaign_send_confirm", args=[campaign.pk]),
                {"confirmation_text": "Policy"},
                follow=True,
            )
        self.assertContains(confirm, 'id="sms-quiet-hours-notice"')
        self.assertContains(response, "SMS quiet hours")
        start.assert_not_called()
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "draft")

    def test_the_status_counts_opted_out_recipients(self):
        campaign = self.campaign()
        SmsRecipientLog.objects.create(campaign=campaign, phone_number="+12095550101", status="opted_out")
        data = self.client.get(reverse("admin:mail_smscampaign_send_status_json", args=[campaign.pk])).json()
        self.assertEqual(data["opted_out"], 1)

    def test_the_composer_gets_its_counter(self):
        response = self.client.get(reverse("admin:mail_smscampaign_change", args=[self.campaign().pk]))
        self.assertContains(response, 'id="sms-composer-settings"')
        self.assertContains(response, "mail/js/sms-composer.js")

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_saving_a_link_placeholder_needs_links_allowed(self):
        data = {
            "name": "Links",
            "message": "Sign in: {{login_link}}",
            "phone_policy": "verified_opt_in",
            "audience_type": "subscribers",
            "login_redirect_path": "/account",
            "link_validity_days": "3",
            "recipient_logs-TOTAL_FORMS": "0",
            "recipient_logs-INITIAL_FORMS": "0",
        }
        response = self.client.post(reverse("admin:mail_smscampaign_add"), data)
        self.assertContains(response, "Links in SMS are turned off")
        sms_settings(links_enabled=True)
        response = self.client.post(reverse("admin:mail_smscampaign_add"), {**data, "link_validity_days": "30"})
        self.assertContains(response, "Choose 1 to 14 days.")
        response = self.client.post(reverse("admin:mail_smscampaign_add"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SmsCampaign.objects.get(name="Links").link_validity_days, 3)

    @override_settings(BACKGROUND_JOBS_ENABLED=False, ADMIN_REQUIRE_CONFIRMATION=False)
    def test_resuming_in_quiet_hours_says_why_nothing_happened(self):
        campaign = self.campaign()
        with at(QUIET_MOMENT):
            response = self.client.post(
                reverse("admin:mail_smscampaign_changelist"),
                {"action": "resume_paused_recipients_action", "_selected_action": [str(campaign.pk)]},
                follow=True,
            )
        self.assertContains(response, "SMS quiet hours")
