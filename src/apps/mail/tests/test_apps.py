"""Coverage for the mail AppConfig post_migrate recovery hook."""

from unittest.mock import patch

from django.test import TestCase

from apps.mail.apps import _reset_stuck_sending_campaigns
from apps.mail.models import EmailCampaign, SmsCampaign


class ResetStuckSendingCampaignsTests(TestCase):
    def test_resets_stuck_email_and_sms_campaigns(self):
        email = EmailCampaign.objects.create(subject="Stuck", body="b", status="sending")
        sms = SmsCampaign.objects.create(name="Stuck SMS", message="m", status="sending")

        _reset_stuck_sending_campaigns(sender=None)

        email.refresh_from_db()
        sms.refresh_from_db()
        self.assertEqual(email.status, "failed")
        self.assertEqual(sms.status, "failed")
        self.assertIn("worker restarted mid-send", email.error_message)
        self.assertIn("worker restarted mid-send", sms.error_message)

    def test_import_failure_is_swallowed(self):
        # Force the inner model import to fail; the hook must return silently.
        with patch.dict("sys.modules", {"apps.mail.models": None}):
            # Importing from a None module raises ImportError, exercising the except branch.
            _reset_stuck_sending_campaigns(sender=None)
