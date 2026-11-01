"""'Resume paused recipients' sends exactly the recipients the delivery limits paused: queued for the worker when
background jobs are on, otherwise by a new in-process runner."""

from unittest.mock import patch

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, BackgroundJob, EmailServiceConfig
from apps.core.services.email import DeliveryResult
from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch import aggregate_email_campaign, resume_paused_email_recipients

DELIVER = "apps.mail.services.send_campaign.transport.deliver_email"
START_TASK = "apps.mail.services.campaign.dispatch.resume.start_in_process_task"


def run_now(target, *args, **_options):
    target(*args)


class ResumePausedRecipientsTests(TestCase):
    def setUp(self):
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email="i2g@example.edu")
        self.campaign = EmailCampaign.objects.create(subject="Hi", body="<p>Hello</p>", audience_type="manual")
        member = make_member(email="paused@example.com", first_name="Pat")
        self.sent = self.log("sent@example.com", "sent")
        self.paused = [self.log("paused@example.com", "paused", member=member), self.log("other@example.com", "paused")]
        aggregate_email_campaign(self.campaign.pk)
        self.campaign.refresh_from_db()

    def log(self, address, status, member=None):
        return RecipientLog.objects.create(
            campaign=self.campaign, email_address=address, member=member, status=status, attempts=1
        )

    def test_the_paused_campaign_is_partial(self):
        self.assertEqual(self.campaign.status, "partial")

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    def test_without_the_worker_only_the_paused_recipients_are_sent_again(self):
        with (
            patch(START_TASK, side_effect=run_now),
            patch(DELIVER, return_value=DeliveryResult(provider="ses", message_id="again")) as deliver,
        ):
            self.assertEqual(resume_paused_email_recipients(self.campaign), 2)

        self.assertEqual(
            sorted(call.args[0].to[0] for call in deliver.call_args_list),
            sorted(["paused@example.com", "other@example.com"]),
        )
        self.assertEqual(set(RecipientLog.objects.values_list("status", flat=True)), {"sent"})
        self.campaign.refresh_from_db()
        self.assertEqual((self.campaign.status, self.campaign.sent_count), ("sent", 3))

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_with_the_worker_the_paused_recipients_are_queued_on_the_campaign_lane(self):
        self.assertEqual(resume_paused_email_recipients(self.campaign), 2)

        jobs = BackgroundJob.objects.filter(kind="mail.email_recipient")
        self.assertEqual({job.payload["recipient_log_id"] for job in jobs}, {str(log.pk) for log in self.paused})
        self.assertEqual({job.priority for job in jobs}, {100})
        self.assertEqual(sorted(RecipientLog.objects.values_list("status", flat=True)), ["pending", "pending", "sent"])
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "sending")

    def test_a_campaign_still_sending_or_without_paused_recipients_is_left_alone(self):
        EmailCampaign.objects.filter(pk=self.campaign.pk).update(status="sending")
        with patch(START_TASK) as start:
            self.assertEqual(resume_paused_email_recipients(self.campaign), 0)
        RecipientLog.objects.filter(status="paused").update(status="failed")
        EmailCampaign.objects.filter(pk=self.campaign.pk).update(status="partial")
        with patch(START_TASK) as start:
            self.assertEqual(resume_paused_email_recipients(self.campaign), 0)

        start.assert_not_called()


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False, BACKGROUND_JOBS_ENABLED=True)
class ResumePausedRecipientsAdminTests(TestCase):
    def setUp(self):
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.campaign = EmailCampaign.objects.create(subject="Hi", body="<p>Hello</p>", status="partial")
        RecipientLog.objects.create(campaign=self.campaign, email_address="a@example.com", status="paused")
        self.url = reverse("admin:mail_emailcampaign_changelist")

    def post(self):
        data = {"action": "resume_paused_recipients_action", ACTION_CHECKBOX_NAME: [str(self.campaign.pk)]}
        return self.client.post(self.url, data, follow=True)

    def test_the_action_resumes_and_says_how(self):
        response = self.post()

        self.assertContains(response, "Resumed 1 paused recipient(s): queued for the background worker.")
        self.assertEqual(BackgroundJob.objects.filter(kind="mail.email_recipient").count(), 1)

    def test_nothing_to_resume_is_reported(self):
        RecipientLog.objects.update(status="sent")

        self.assertContains(self.post(), "No paused recipients to resume")
