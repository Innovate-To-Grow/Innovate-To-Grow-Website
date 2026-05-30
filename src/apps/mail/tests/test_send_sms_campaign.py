from unittest.mock import patch

from django.test import TestCase

from apps.authn.models import ContactPhone
from apps.core.models import AWSCredentialConfig
from apps.event.tests.helpers import make_member
from apps.mail.models import SmsCampaign, SmsRecipientLog
from apps.mail.services.send_sms_campaign import send_sms_campaign


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


def _add_phone(member, number, *, subscribe=True, verified=True):
    return ContactPhone.objects.create(
        member=member,
        phone_number=number,
        region="1-US",
        subscribe=subscribe,
        verified=verified,
    )


class SendSmsCampaignTests(TestCase):
    def setUp(self):
        AWSCredentialConfig.objects.all().delete()
        self.sender = make_member(email="sender@example.com", first_name="Sender", last_name="User")

    @patch("apps.mail.services.send_sms_campaign.publish_plain_sms", return_value="sns-msg-1")
    def test_send_sms_campaign_records_successful_recipient_log(self, mock_publish):
        _make_sms_config()
        member = make_member(email="recipient@example.com", first_name="Ada", last_name="Lovelace")
        _add_phone(member, "2095551001")
        campaign = SmsCampaign.objects.create(message="Hello {{first_name}}", audience_type="all_members")

        result = send_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 1, "sent": 1, "failed": 0})
        self.assertEqual(campaign.status, "sent")
        log = SmsRecipientLog.objects.get(campaign=campaign)
        self.assertEqual(log.status, "sent")
        self.assertEqual(log.provider, "aws_sns")
        self.assertEqual(log.sns_message_id, "sns-msg-1")
        mock_publish.assert_called_once_with(phone_number="+12095551001", message="Hello Ada")

    def test_send_sms_campaign_fails_when_sns_is_not_configured(self):
        member = make_member(email="recipient@example.com")
        _add_phone(member, "2095551001")
        campaign = SmsCampaign.objects.create(message="Hello", audience_type="all_members")

        with self.assertRaises(RuntimeError):
            send_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertIn("SMS delivery is not configured", campaign.error_message)

    @patch("apps.mail.services.send_sms_campaign.publish_plain_sms")
    def test_send_sms_campaign_records_partial_failures(self, mock_publish):
        _make_sms_config()
        first = make_member(email="first@example.com")
        second = make_member(email="second@example.com")
        _add_phone(first, "2095551001")
        _add_phone(second, "2095551002")
        mock_publish.side_effect = ["sns-msg-1", RuntimeError("boom")]
        campaign = SmsCampaign.objects.create(message="Hello", audience_type="all_members")

        result = send_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 2, "sent": 1, "failed": 1})
        self.assertEqual(campaign.status, "sent")
        self.assertEqual(SmsRecipientLog.objects.filter(campaign=campaign, status="sent").count(), 1)
        failed = SmsRecipientLog.objects.get(campaign=campaign, status="failed")
        self.assertEqual(failed.error_message, "boom")

    @patch("apps.mail.services.send_sms_campaign.publish_plain_sms", return_value="sns-id")
    def test_send_sms_campaign_persists_progress_every_ten_recipients(self, mock_publish):
        _make_sms_config()
        # 10 manual phones trigger the (sent+failed) % 10 == 0 periodic save.
        phones = "\n".join(f"+1209555{1000 + i:04d}" for i in range(10))
        campaign = SmsCampaign.objects.create(message="Hi", audience_type="manual", manual_phones=phones)

        result = send_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 10, "sent": 10, "failed": 0})
        self.assertEqual(campaign.status, "sent")
        self.assertEqual(mock_publish.call_count, 10)
