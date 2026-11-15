from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import SmsCampaign, SmsRecipientLog

from ....services.sms.policy.policy_helpers import QUIET_MOMENT, add_phone, at, opt_out, sms_aws_config, sms_settings


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
