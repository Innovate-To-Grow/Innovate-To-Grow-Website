from django.test import TestCase

from apps.core.models import BackgroundJob, EmailServiceConfig
from apps.core.services.background_jobs import claim_jobs, enqueue_job
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.tests.services.campaigns.jobs.queue.test_pacing import make_graph_sender


class QueuedCampaignOrderTests(TestCase):
    def setUp(self):
        self.sender = make_superuser()
        self.campaign = EmailCampaign.objects.create(
            name="Spaced",
            subject="Hi",
            body="<p>Body</p>",
            audience_type="manual",
            manual_emails="a@example.com\nb@example.com\nc@example.com",
        )

    def campaign_jobs(self):
        return list(BackgroundJob.objects.filter(kind="mail.email_recipient").order_by("available_at", "created_at"))

    def test_graph_recipient_jobs_are_all_due_at_once_and_logs_mirror_them(self):
        # The limiter paces them as they run; launch no longer spreads them out.
        make_graph_sender()

        queue_email_campaign(self.campaign, sent_by=self.sender)

        jobs = self.campaign_jobs()
        self.assertEqual(len({job.available_at for job in jobs}), 1)
        self.assertEqual({job.priority for job in jobs}, {100})
        for job in jobs:
            log = RecipientLog.objects.get(pk=job.payload["recipient_log_id"])
            self.assertEqual(log.available_at, job.available_at)

    def test_work_queued_during_a_graph_campaign_runs_before_its_later_recipients(self):
        make_graph_sender()
        queue_email_campaign(self.campaign, sent_by=self.sender)
        enqueue_job(kind="event.ticket_email", dedupe_key="later", payload={})

        claimed = claim_jobs(batch_size=10)

        # A ticket (transactional, priority 10) is claimed before the campaign's recipients, all due already.
        self.assertEqual([job.kind for job in claimed], ["event.ticket_email"] + ["mail.email_recipient"] * 3)

    def test_ses_campaign_jobs_are_all_due_at_once(self):
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email="a@example.com")

        queue_email_campaign(self.campaign, sent_by=self.sender)

        self.assertEqual(len({job.available_at for job in self.campaign_jobs()}), 1)
        self.assertEqual(len(claim_jobs(batch_size=10)), 3)
