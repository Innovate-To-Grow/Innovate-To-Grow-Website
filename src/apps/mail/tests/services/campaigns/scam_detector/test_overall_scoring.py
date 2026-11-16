from django.test import SimpleTestCase

from apps.mail.services.scam_detector import (
    HIGH_THRESHOLD,
    MEDIUM_THRESHOLD,
    analyze_email,
)
from apps.mail.tests.services.campaigns.scam_detector.test_scam_detector import _msg


class OverallScoringTest(SimpleTestCase):
    def test_medium_risk_threshold(self):
        result = analyze_email(
            _msg(
                from_name="",
                subject="Urgent: Verify your account now",
                text="Dear Customer, click here immediately.",
            )
        )
        self.assertGreaterEqual(result["score"], MEDIUM_THRESHOLD)
        self.assertIn(result["risk_level"], ("medium", "high"))

    def test_high_risk_combined_signals(self):
        result = analyze_email(
            _msg(
                from_name="Amazon Security",
                from_email="security@totally-not-amazon.com",
                subject="URGENT: YOUR ACCOUNT HAS BEEN SUSPENDED",
                text="Dear Customer, your account has been suspended. "
                "Click here immediately to verify your password and social security number. "
                "Failure to respond within 24 hours will result in permanent closure.",
                html='<a href="http://192.168.1.1/phish">amazon.com/verify</a>'
                '<a href="https://bit.ly/fake">Verify Now</a>'
                '<div style="display:none">tracking pixel</div>',
            )
        )
        self.assertGreaterEqual(result["score"], HIGH_THRESHOLD)
        self.assertEqual(result["risk_level"], "high")
        self.assertGreater(len(result["reasons"]), 3)

    def test_legitimate_email_stays_low(self):
        result = analyze_email(
            _msg(
                from_name="John Smith",
                from_email="john.smith@ucmerced.edu",
                subject="Team meeting agenda - April 10",
                text="Hi everyone,\n\nHere is the agenda for our meeting tomorrow.\n\nBest,\nJohn",
            )
        )
        self.assertEqual(result["risk_level"], "low")
        self.assertLess(result["score"], MEDIUM_THRESHOLD)
