from apps.core.services.background_jobs import claim_jobs
from apps.core.services.background_jobs.worker import run_claimed_job
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.tests.admin.mail_settings_graph.sending_method.test_sending_method_reaches_all_mail import (
    _SendingMethodReachesAllMailCase,
)


class SendingMethodReachesAllMailTests(_SendingMethodReachesAllMailCase):
    def test_a_campaign_queued_before_the_switch_goes_out_through_the_new_method(self):
        # Production can send campaigns from the background worker: each recipient's job reads the method as it runs.
        campaign = EmailCampaign.objects.create(
            name="Queued",
            subject="Hello",
            body="<p>Body</p>",
            audience_type="manual",
            manual_emails="worker@example.com",
        )
        queue_email_campaign(campaign, sent_by=self.superuser)
        self.use_for_email("smtp")

        jobs = claim_jobs()
        for job in jobs:
            run_claimed_job(job)

        self.assertTrue(jobs)
        self.assertEqual(self.transports.recipients("smtp"), ["worker@example.com"])
        self.assertEqual(self.transports.recipients("ses"), [])
        self.assertEqual(RecipientLog.objects.get(campaign=campaign).status, "sent")
