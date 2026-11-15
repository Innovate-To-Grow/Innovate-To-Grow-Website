"""Coverage for mail startup behavior."""

from django.test import TestCase

from apps.mail.apps import MailConfig
from apps.mail.models import EmailCampaign, SmsCampaign


class MailAppStartupTests(TestCase):
    def test_startup_does_not_guess_outcomes_for_in_flight_campaigns(self):
        email = EmailCampaign.objects.create(subject="Stuck", body="b", status="sending")
        sms = SmsCampaign.objects.create(name="Stuck SMS", message="m", status="sending")

        MailConfig("mail", __import__("apps.mail", fromlist=["mail"])).ready()

        email.refresh_from_db()
        sms.refresh_from_db()
        self.assertEqual(email.status, "sending")
        self.assertEqual(sms.status, "sending")
