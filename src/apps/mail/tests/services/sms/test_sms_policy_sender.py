"""The SMS policy on the in-process sender (background jobs off) and on starting a send: the audience leaves out
opted-out numbers, a number found opted out at send time is logged "Opted out", quiet hours pause the rest or refuse
the start, and a message whose links are off cannot start. ``publish_plain_sms`` stands in for AWS."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.authn.services.sms import PhoneNumberOptedOut
from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import SmsCampaign, SmsRecipientLog
from apps.mail.models.sms_campaign import LINKS_OFF_MESSAGE
from apps.mail.services.campaign.dispatch import dispatch_sms_campaign, resume_paused_sms_recipients
from apps.mail.services.sms.audience import get_sms_recipients
from apps.mail.services.sms.errors import LinksDisabled, QuietHoursActive
from apps.mail.services.sms.quiet_hours import PAUSED_LOG_MESSAGE
from apps.mail.services.sms.sender import send_sms_campaign

from .policy_helpers import QUIET_ENDS, QUIET_MOMENT, add_phone, at, opt_out, sms_aws_config, sms_settings

PUBLISH = "apps.mail.services.sms.sender.publish_plain_sms"


class SmsPolicySenderTests(TestCase):
    def setUp(self):
        sms_aws_config()
        self.sender = make_superuser()
        self.ada = make_member(email="ada@example.com", first_name="Ada")
        self.bo = make_member(email="bo@example.com", first_name="Bo")
        add_phone(self.ada, "2095550101")
        add_phone(self.bo, "2095550102")

    def campaign(self, message="Hello {{first_name}}"):
        return SmsCampaign.objects.create(message=message, audience_type="subscribers")

    def test_the_audience_leaves_out_opted_out_numbers_and_says_how_many(self):
        opt_out("+12095550102")
        recipients = get_sms_recipients(self.campaign())
        self.assertEqual([row["phone"] for row in recipients], ["+12095550101"])
        self.assertEqual([row["phone"] for row in recipients.skipped], ["+12095550102"])

    @patch(PUBLISH, return_value="msg")
    def test_an_opted_out_number_is_never_sent_to(self, publish):
        opt_out("+12095550102")
        result = send_sms_campaign(self.campaign(), sent_by=self.sender)
        self.assertEqual(result, {"total": 1, "sent": 1, "failed": 0})
        publish.assert_called_once()
        self.assertEqual(publish.call_args.kwargs["phone_number"], "+12095550101")

    @patch(PUBLISH, return_value="msg")
    def test_a_number_that_opts_out_during_the_send_is_logged_opted_out(self, publish):
        campaign = self.campaign()
        resolved = get_sms_recipients(campaign)
        opt_out("+12095550102")
        with patch("apps.mail.services.sms.sender.get_sms_recipients", return_value=resolved):
            send_sms_campaign(campaign, sent_by=self.sender)

        logs = {log.phone_number: log for log in SmsRecipientLog.objects.filter(campaign=campaign)}
        self.assertEqual(logs["+12095550102"].status, "opted_out")
        self.assertEqual(logs["+12095550101"].status, "sent")
        campaign.refresh_from_db()
        self.assertEqual((campaign.status, campaign.failed_count), ("sent", 0))

    @patch(PUBLISH, side_effect=PhoneNumberOptedOut())
    def test_aws_refusing_a_number_as_opted_out_is_not_a_failure(self, _publish):
        campaign = self.campaign()
        send_sms_campaign(campaign, sent_by=self.sender)
        self.assertEqual(set(SmsRecipientLog.objects.values_list("status", flat=True)), {"opted_out"})
        campaign.refresh_from_db()
        self.assertEqual((campaign.status, campaign.failed_count), ("sent", 0))

    @patch(PUBLISH, return_value="msg")
    def test_quiet_hours_pause_every_remaining_recipient(self, publish):
        campaign = self.campaign()
        with at(QUIET_MOMENT):
            send_sms_campaign(campaign, sent_by=self.sender)
        publish.assert_not_called()
        self.assertEqual(
            set(SmsRecipientLog.objects.values_list("status", "error_message")), {("paused", PAUSED_LOG_MESSAGE)}
        )
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "partial")

    @patch(PUBLISH, return_value="msg")
    def test_links_turned_off_fail_each_recipient_with_that_reason(self, publish):
        campaign = self.campaign("Sign in {{login_link}}")
        send_sms_campaign(campaign, sent_by=self.sender)
        publish.assert_not_called()
        self.assertEqual(
            set(SmsRecipientLog.objects.values_list("status", "error_message")), {("failed", LINKS_OFF_MESSAGE)}
        )

    @override_settings(FRONTEND_URL="https://i2g.example.edu")
    @patch(PUBLISH, return_value="msg")
    def test_links_are_issued_once_per_campaign_when_allowed(self, publish):
        sms_settings(links_enabled=True)
        send_sms_campaign(self.campaign("Event: {{login_link}}"), sent_by=self.sender)
        messages = [call.kwargs["message"] for call in publish.call_args_list]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0], messages[1])
        self.assertIn("https://i2g.example.edu/l/", messages[0])


@override_settings(BACKGROUND_JOBS_ENABLED=False)
class StartingAnSmsSendTests(TestCase):
    def setUp(self):
        sms_aws_config()
        self.sender = make_superuser()
        self.campaign = SmsCampaign.objects.create(message="Hi", audience_type="manual", manual_phones="+12095550101")

    @patch("apps.mail.services.campaign.dispatch.launch.start_in_process_task")
    def test_the_in_process_sender_cannot_wait_for_quiet_hours(self, start):
        with at(QUIET_MOMENT), self.assertRaises(QuietHoursActive) as caught:
            dispatch_sms_campaign(self.campaign, sent_by=self.sender)
        self.assertEqual(caught.exception.until, QUIET_ENDS)
        start.assert_not_called()
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "draft")

    @patch("apps.mail.services.campaign.dispatch.launch.start_in_process_task")
    def test_a_message_whose_links_are_off_cannot_start(self, start):
        SmsCampaign.objects.filter(pk=self.campaign.pk).update(message="{{ticket_link}}")
        self.campaign.refresh_from_db()
        with self.assertRaises(LinksDisabled):
            dispatch_sms_campaign(self.campaign, sent_by=self.sender)
        start.assert_not_called()

    def test_resuming_in_process_refuses_during_quiet_hours(self):
        with at(QUIET_MOMENT), self.assertRaises(QuietHoursActive):
            resume_paused_sms_recipients(self.campaign)
