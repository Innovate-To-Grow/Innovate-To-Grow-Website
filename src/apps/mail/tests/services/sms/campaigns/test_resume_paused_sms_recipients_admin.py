from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import BackgroundJob
from apps.event.tests.helpers import make_superuser
from apps.mail.models import SmsCampaign, SmsRecipientLog
from apps.mail.tests.services.sms.campaigns.test_sms_delivery_rate import PHONES


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False, BACKGROUND_JOBS_ENABLED=True)
class ResumePausedSmsRecipientsAdminTests(TestCase):
    def setUp(self):
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.campaign = SmsCampaign.objects.create(
            name="Paused", message="Hi", audience_type="manual", status="partial"
        )
        SmsRecipientLog.objects.create(campaign=self.campaign, phone_number=PHONES[0], status="paused")
        self.url = reverse("admin:mail_smscampaign_changelist")

    def post(self):
        data = {"action": "resume_paused_recipients_action", ACTION_CHECKBOX_NAME: [str(self.campaign.pk)]}
        return self.client.post(self.url, data, follow=True)

    def test_the_action_resumes_and_says_how(self):
        response = self.post()

        self.assertContains(response, "Resumed 1 paused recipient(s): queued for the background worker.")
        self.assertEqual(BackgroundJob.objects.filter(kind="mail.sms_recipient").count(), 1)

    def test_nothing_to_resume_is_reported(self):
        SmsRecipientLog.objects.update(status="sent")

        self.assertContains(self.post(), "No paused recipients to resume")
