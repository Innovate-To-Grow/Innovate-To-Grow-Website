"""Mail → SMS Settings, SMS Opt-outs, SMS Links and Ticket SMS in the admin, and what Broadcast SMS shows before a
send (estimate, opted-out recipients, links that are off, quiet hours). AWS is never called."""

from datetime import time

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import SmsConfig

from ....services.sms.policy.policy_helpers import QUIET_MOMENT, at

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
