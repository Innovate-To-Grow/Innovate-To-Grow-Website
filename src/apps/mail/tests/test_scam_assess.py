"""Coverage for the on-demand scam assessment and optional LLM classifier."""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.core.models import AWSCredentialConfig
from apps.mail.services.scam_detector import analyze_email, assess_email
from apps.mail.services.scam_detector.llm_classifier import (
    _build_prompt,
    _call_bedrock,
    _normalize,
    _parse_json,
    llm_review,
)

_LLM_PATH = "apps.mail.services.scam_detector.llm_classifier.invoke_bedrock"


def _medium_msg(**overrides):
    base = {
        "uid": "42",
        "from_name": "",
        "from_email": "alice@example.com",
        "subject": "Urgent: verify your account",
        "text": "hello",
        "html": "",
        "to": [],
    }
    base.update(overrides)
    return base


def _aws_configured():
    return AWSCredentialConfig.objects.create(
        name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
    )


class LlmParsingTests(SimpleTestCase):
    def test_build_prompt_prefers_text(self):
        prompt = _build_prompt({"text": "hello body", "html": "<p>x</p>", "subject": "Hi"})
        self.assertIn("hello body", prompt)
        self.assertIn("Subject: Hi", prompt)

    def test_build_prompt_falls_back_to_html(self):
        prompt = _build_prompt({"text": "", "html": "<p>html body</p>"})
        self.assertIn("html body", prompt)

    def test_parse_json_extracts_object(self):
        self.assertEqual(_parse_json('noise {"verdict": "scam"} trailing')["verdict"], "scam")

    def test_parse_json_handles_garbage(self):
        self.assertIsNone(_parse_json("no json here"))
        self.assertIsNone(_parse_json(""))
        self.assertIsNone(_parse_json("{not valid}"))

    def test_parse_json_rejects_non_object(self):
        self.assertIsNone(_parse_json("[1, 2, 3]"))

    def test_normalize_clamps_and_defaults(self):
        result = _normalize({"verdict": "weird", "confidence": 5, "risk_score": 999, "reasons": ["a", "", "b"]})
        self.assertEqual(result["verdict"], "suspicious")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["risk_score"], 100)
        self.assertEqual(result["reasons"], ["a", "b"])

    def test_normalize_handles_bad_types(self):
        result = _normalize({"confidence": "x", "risk_score": "y", "reasons": None})
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["risk_score"], 0)
        self.assertEqual(result["reasons"], [])


class LlmReviewTests(TestCase):
    def test_unconfigured_aws_returns_none(self):
        self.assertIsNone(llm_review(_medium_msg()))

    def test_success_returns_normalized(self):
        _aws_configured()
        payload = {"text": '{"verdict": "scam", "confidence": 0.9, "risk_score": 95, "reasons": ["spoofed"]}'}
        with patch(_LLM_PATH, return_value=payload):
            review = llm_review(_medium_msg())
        self.assertEqual(review["verdict"], "scam")
        self.assertEqual(review["reasons"], ["spoofed"])

    def test_bedrock_exception_returns_none(self):
        _aws_configured()
        with patch(_LLM_PATH, side_effect=RuntimeError("boom")):
            self.assertIsNone(llm_review(_medium_msg()))

    def test_unparseable_output_returns_none(self):
        _aws_configured()
        with patch(_LLM_PATH, return_value={"text": "sorry, I cannot help"}):
            self.assertIsNone(llm_review(_medium_msg()))

    def test_call_bedrock_non_dict_response_returns_empty(self):
        _aws_configured()
        with patch(_LLM_PATH, return_value="not a dict"):
            self.assertEqual(_call_bedrock("prompt"), "")


class AssessEmailTests(TestCase):
    def test_low_risk_skips_llm(self):
        _aws_configured()
        clean = _medium_msg(from_name="Alice", subject="Lunch tomorrow", text="See you then.")
        with patch(_LLM_PATH) as mock_llm:
            result = assess_email(clean)
        self.assertEqual(result["risk_level"], "low")
        self.assertNotIn("ai_review", result)
        mock_llm.assert_not_called()

    def test_high_risk_skips_llm(self):
        _aws_configured()
        high_risk = _medium_msg(
            from_name="Amazon Security",
            from_email="security@totally-not-amazon.com",
            subject="URGENT: YOUR ACCOUNT HAS BEEN SUSPENDED",
            text=(
                "Dear Customer, click here immediately to verify your password and "
                "social security number before account closure."
            ),
            html='<a href="http://192.168.1.1/phish">amazon.com/verify</a>',
        )
        with patch(_LLM_PATH) as mock_llm:
            result = assess_email(high_risk)
        self.assertEqual(result["risk_level"], "high")
        mock_llm.assert_not_called()

    def test_medium_escalates_on_scam_verdict_without_persisting_result(self):
        _aws_configured()
        payload = {"text": '{"verdict": "scam", "confidence": 0.95, "risk_score": 96, "reasons": ["spoofed sender"]}'}
        with patch(_LLM_PATH, return_value=payload) as mock_llm:
            first = assess_email(_medium_msg())
            second = assess_email(_medium_msg())
        # A confident high AI score fuses the meter up and re-bands to high.
        self.assertEqual(first["risk_level"], "high")
        self.assertGreaterEqual(first["score_percent"], 70)
        self.assertEqual(first["ai_review"]["reasons"], ["spoofed sender"])
        self.assertEqual(second["risk_level"], "high")
        # The result is recomputed instead of stored after analysis.
        self.assertEqual(mock_llm.call_count, 2)

    def test_medium_legitimate_fuses_down_to_low(self):
        _aws_configured()
        payload = {"text": '{"verdict": "legitimate", "confidence": 0.9, "risk_score": 5, "reasons": []}'}
        with patch(_LLM_PATH, return_value=payload):
            result = assess_email(_medium_msg())
        self.assertEqual(result["risk_level"], "low")
        self.assertLess(result["score_percent"], 40)
        self.assertIn("likely legitimate", result["summary"])

    def test_medium_partial_fusion_keeps_medium(self):
        _aws_configured()
        rule_only = analyze_email(_medium_msg())
        payload = {"text": '{"verdict": "suspicious", "confidence": 0.5, "risk_score": 60, "reasons": ["odd link"]}'}
        with patch(_LLM_PATH, return_value=payload):
            result = assess_email(_medium_msg())
        self.assertEqual(result["risk_level"], "medium")
        # Fused meter sits between the rule-only meter and the AI's risk score.
        self.assertNotEqual(result["score_percent"], rule_only["score_percent"])
        self.assertLessEqual(result["score_percent"], 60)
