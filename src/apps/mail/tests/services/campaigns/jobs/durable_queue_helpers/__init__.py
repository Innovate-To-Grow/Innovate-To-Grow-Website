"""Shared fixtures for the durable campaign queue tests: a sender and queued email / SMS recipients."""

from django.test import TestCase

from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog, SmsCampaign, SmsRecipientLog
from apps.mail.services.campaign.dispatch import (
    queue_email_campaign,
    queue_sms_campaign,
)


def _provider_failure(exc):
    def fail(*, before_provider_call, **_kwargs):
        before_provider_call()
        raise exc

    return fail


class DurableCampaignQueueTestCase(TestCase):
    def setUp(self):
        self.sender = make_superuser()

    def _queued_email(self):
        campaign = EmailCampaign.objects.create(
            name="Worker email",
            subject="Hello {{first_name}}",
            body="<p>Body</p>",
            audience_type="manual",
            manual_emails="worker@example.com",
        )
        queue_email_campaign(campaign, sent_by=self.sender)
        return campaign, RecipientLog.objects.get(campaign=campaign)

    def _queued_sms(self):
        campaign = SmsCampaign.objects.create(
            name="Worker SMS",
            message="Hello {{first_name}}",
            audience_type="manual",
            manual_phones="+12095550101",
        )
        queue_sms_campaign(campaign, sent_by=self.sender)
        return campaign, SmsRecipientLog.objects.get(campaign=campaign)
