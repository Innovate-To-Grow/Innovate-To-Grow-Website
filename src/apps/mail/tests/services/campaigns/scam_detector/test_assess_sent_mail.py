from unittest.mock import patch

from django.test import TestCase

from apps.mail.services.scam_detector import analyze_email, assess_email
from apps.mail.tests.services.campaigns.scam_detector.test_scam_assess import _LLM_PATH, _aws_configured, _medium_msg


class AssessSentMailTests(TestCase):
    """Sent mail never reaches Bedrock: the site wrote it and it can hold live codes (a password-reset code scores
    in the medium band because of the word "password"). It keeps the rule result."""

    def setUp(self):
        _aws_configured()

    def assert_rule_result_without_ai(self, msg, **kwargs):
        with patch(_LLM_PATH) as invoke:
            result = assess_email(msg, **kwargs)
        invoke.assert_not_called()
        self.assertEqual(result, analyze_email(msg))
        self.assertEqual(result["risk_level"], "medium")

    def test_the_sent_folder_is_never_sent_to_the_ai_reviewer(self):
        for folder in ("SENT", "sent"):
            with self.subTest(folder=folder):
                self.assert_rule_result_without_ai(_medium_msg(), folder=folder)

    def test_a_message_from_the_site_mailbox_is_never_sent_to_the_ai_reviewer(self):
        self.assert_rule_result_without_ai(_medium_msg(from_own_mailbox=True), folder="INBOX")

    def test_a_password_reset_code_in_sent_items_stays_on_site(self):
        reset = _medium_msg(
            from_name="Innovate to Grow",
            from_email="i2g@ucmerced.edu",
            subject="Password reset code - Innovate to Grow",
            text="Use the code below to reset your password. 482913",
            from_own_mailbox=True,
        )

        self.assert_rule_result_without_ai(reset, folder="SENT")

    def test_inbox_mail_in_the_medium_band_still_gets_the_ai_opinion(self):
        payload = {"text": '{"verdict": "scam", "confidence": 0.9, "risk_score": 90, "reasons": ["spoofed"]}'}
        with patch(_LLM_PATH, return_value=payload) as invoke:
            result = assess_email(_medium_msg(from_own_mailbox=False), folder="INBOX")

        invoke.assert_called_once()
        self.assertIn("ai_review", result)
