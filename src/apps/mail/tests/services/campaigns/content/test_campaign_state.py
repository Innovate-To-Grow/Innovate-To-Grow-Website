from django.test import SimpleTestCase

from apps.mail.services.campaign.state import campaign_state


class CampaignStateTests(SimpleTestCase):
    def test_derives_every_terminal_and_active_state(self):
        cases = (
            ({"total": 0, "sent": 0, "failed": 0}, "sent"),
            ({"total": 3, "sent": 3, "failed": 0}, "sent"),
            ({"total": 3, "sent": 2, "failed": 1}, "partial"),
            ({"total": 3, "sent": 0, "failed": 3}, "failed"),
            ({"total": 3, "sent": 0, "failed": 0, "active": 3}, "queued"),
            ({"total": 3, "sent": 1, "failed": 0, "active": 2}, "sending"),
            ({"total": 3, "sent": 0, "failed": 1, "active": 2}, "sending"),
        )

        for counts, expected in cases:
            with self.subTest(counts=counts):
                self.assertEqual(campaign_state(**counts), expected)
