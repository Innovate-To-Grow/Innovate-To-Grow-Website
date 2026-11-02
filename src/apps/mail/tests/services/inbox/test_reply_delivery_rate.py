"""Inbox replies go through the delivery-rate limiter on the transactional lane."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.models import AWSCredentialConfig, DeliveryRateState, EmailServiceConfig
from apps.core.services.delivery_rates import Lane, ses_identity
from apps.core.tests.services.delivery_rates.helpers import FakeClock, spy_on_email_admissions
from apps.mail.services.inbox.reply import REPLY_SEND_FAILURE_MESSAGE, send_reply


class ReplyDeliveryRateTests(TestCase):
    def setUp(self):
        self.clock = FakeClock(timezone.now()).install(self)
        self.aws = AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email="i2g@example.edu")
        patcher = patch("apps.core.services.email.ses.boto3.client")
        self.ses = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.ses.send_raw_email.return_value = {"MessageId": "ses-1"}
        self.admissions = spy_on_email_admissions(self)

    def reply(self):
        return send_reply(
            to_email="sender@example.com", subject="Re: Hi", reply_body="Thanks", cc_email="cc@example.com"
        )

    def test_a_reply_is_admitted_for_every_recipient_on_the_transactional_lane(self):
        self.assertEqual(self.reply(), "")

        self.assertEqual(self.admissions.call_args.kwargs["lane"], Lane.TRANSACTIONAL)
        self.assertEqual(self.admissions.call_args.kwargs["budget_cost"], 2)

    def test_a_held_back_reply_is_reported_and_not_sent(self):
        DeliveryRateState.objects.create(
            channel="ses_send",
            identity=ses_identity(self.aws.pk, "us-west-2"),
            cooldown_group="ses:us-west-2",
            cooldown_until=self.clock.now() + timedelta(minutes=5),
        )

        self.assertEqual(self.reply(), REPLY_SEND_FAILURE_MESSAGE)
        self.ses.send_raw_email.assert_not_called()
