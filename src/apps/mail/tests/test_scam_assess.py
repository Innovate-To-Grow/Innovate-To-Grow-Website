"""Coverage for ScamDetectorConfig, the LLM classifier, assess_email, and the admin."""

from unittest.mock import patch

from django.contrib import admin as django_admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig
from apps.event.tests.helpers import make_superuser
from apps.mail.admin.scam_config import ScamDetectorConfigAdmin
from apps.mail.models import ScamDetectorConfig
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


class ScamDetectorConfigModelTests(TestCase):
    def test_load_returns_unsaved_defaults_when_empty(self):
        config = ScamDetectorConfig.load()
        self.assertIsNone(config.pk)
        self.assertTrue(config.ai_review_enabled)
        self.assertEqual(config.medium_threshold, 3)

    def test_load_prefers_active(self):
        ScamDetectorConfig.objects.create(name="old", is_active=False)
        active = ScamDetectorConfig.objects.create(name="live", is_active=True)
        self.assertEqual(ScamDetectorConfig.load().pk, active.pk)

    def test_load_falls_back_to_most_recent(self):
        ScamDetectorConfig.objects.create(name="only", is_active=False)
        self.assertEqual(ScamDetectorConfig.load().name, "only")

    def test_activation_deactivates_others(self):
        first = ScamDetectorConfig.objects.create(name="first", is_active=True)
        second = ScamDetectorConfig.objects.create(name="second", is_active=True)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)

    def test_brand_keywords_merges_extra(self):
        config = ScamDetectorConfig(extra_brands="Venmo\n  Zelle  \n")
        brands = config.brand_keywords()
        self.assertIn("amazon", brands)
        self.assertIn("venmo", brands)
        self.assertIn("zelle", brands)

    def test_str_shows_active_state(self):
        self.assertEqual(str(ScamDetectorConfig(name="Prod", is_active=True)), "Prod (active)")
        self.assertEqual(str(ScamDetectorConfig(name="Prod", is_active=False)), "Prod")

    def test_is_trusted_sender(self):
        config = ScamDetectorConfig(trusted_senders="ucmerced.edu\ndean@example.com")
        self.assertTrue(config.is_trusted_sender("anyone@ucmerced.edu"))
        self.assertTrue(config.is_trusted_sender("anyone@mail.ucmerced.edu"))
        self.assertTrue(config.is_trusted_sender("dean@example.com"))
        self.assertFalse(config.is_trusted_sender("stranger@evil.com"))
        self.assertFalse(config.is_trusted_sender(""))


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
    def test_disabled_returns_none(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=False)
        self.assertIsNone(llm_review(_medium_msg()))

    def test_unconfigured_aws_returns_none(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=True)
        self.assertIsNone(llm_review(_medium_msg()))

    def test_success_returns_normalized(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=True)
        _aws_configured()
        payload = {"text": '{"verdict": "scam", "confidence": 0.9, "risk_score": 95, "reasons": ["spoofed"]}'}
        with patch(_LLM_PATH, return_value=payload):
            review = llm_review(_medium_msg())
        self.assertEqual(review["verdict"], "scam")
        self.assertEqual(review["reasons"], ["spoofed"])

    def test_bedrock_exception_returns_none(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=True)
        _aws_configured()
        with patch(_LLM_PATH, side_effect=RuntimeError("boom")):
            self.assertIsNone(llm_review(_medium_msg()))

    def test_unparseable_output_returns_none(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=True)
        _aws_configured()
        with patch(_LLM_PATH, return_value={"text": "sorry, I cannot help"}):
            self.assertIsNone(llm_review(_medium_msg()))

    def test_call_bedrock_non_dict_response_returns_empty(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=True)
        _aws_configured()
        with patch(_LLM_PATH, return_value="not a dict"):
            self.assertEqual(_call_bedrock("prompt"), "")


class AssessEmailTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_trusted_sender_short_circuits(self):
        ScamDetectorConfig.objects.create(is_active=True, trusted_senders="example.com")
        with patch(_LLM_PATH) as mock_llm:
            result = assess_email(_medium_msg(from_email="x@example.com"))
        self.assertEqual(result["risk_level"], "low")
        self.assertIn("trusted allowlist", result["summary"])
        mock_llm.assert_not_called()

    def test_low_risk_skips_llm(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=True)
        _aws_configured()
        clean = _medium_msg(from_name="Alice", subject="Lunch tomorrow", text="See you then.")
        with patch(_LLM_PATH) as mock_llm:
            result = assess_email(clean)
        self.assertEqual(result["risk_level"], "low")
        self.assertNotIn("ai_review", result)
        mock_llm.assert_not_called()

    def test_disabled_skips_llm(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=False)
        _aws_configured()
        with patch(_LLM_PATH) as mock_llm:
            result = assess_email(_medium_msg())
        self.assertEqual(result["risk_level"], "medium")
        self.assertNotIn("ai_review", result)
        mock_llm.assert_not_called()

    def test_medium_escalates_on_scam_verdict_and_caches(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=True)
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
        # Second call served from cache.
        mock_llm.assert_called_once()

    def test_medium_legitimate_fuses_down_to_low(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=True)
        _aws_configured()
        payload = {"text": '{"verdict": "legitimate", "confidence": 0.9, "risk_score": 5, "reasons": []}'}
        with patch(_LLM_PATH, return_value=payload):
            result = assess_email(_medium_msg())
        self.assertEqual(result["risk_level"], "low")
        self.assertLess(result["score_percent"], 40)
        self.assertIn("likely legitimate", result["summary"])

    def test_medium_partial_fusion_keeps_medium(self):
        ScamDetectorConfig.objects.create(is_active=True, ai_review_enabled=True)
        _aws_configured()
        rule_only = analyze_email(_medium_msg())
        payload = {"text": '{"verdict": "suspicious", "confidence": 0.5, "risk_score": 60, "reasons": ["odd link"]}'}
        with patch(_LLM_PATH, return_value=payload):
            result = assess_email(_medium_msg())
        self.assertEqual(result["risk_level"], "medium")
        # Fused meter sits between the rule-only meter and the AI's risk score.
        self.assertNotEqual(result["score_percent"], rule_only["score_percent"])
        self.assertLessEqual(result["score_percent"], 60)


class ScamConfigAdminTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def _admin(self):
        return ScamDetectorConfigAdmin(ScamDetectorConfig, django_admin.site)

    def test_changelist_renders_both_status_badges(self):
        ScamDetectorConfig.objects.create(name="live-config", is_active=True)
        ScamDetectorConfig.objects.create(name="old-config", is_active=False)
        response = self.client.get(reverse("admin:mail_scamdetectorconfig_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "live-config")
        self.assertContains(response, "old-config")

    def test_activate_action(self):
        config = ScamDetectorConfig.objects.create(name="c", is_active=False)
        request = RequestFactory().post("/")
        request.session = {}
        request._messages = FallbackStorage(request)
        response = self._admin().activate_this_config(request, str(config.pk))
        config.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(config.is_active)

    def test_delete_permission_blocked_for_active(self):
        request = RequestFactory().get("/")
        request.user = self.admin_user
        active = ScamDetectorConfig.objects.create(name="a", is_active=True)
        inactive = ScamDetectorConfig.objects.create(name="b", is_active=False)
        self.assertFalse(self._admin().has_delete_permission(request, active))
        self.assertTrue(self._admin().has_delete_permission(request, inactive))

    def test_get_actions_drops_bulk_delete(self):
        request = RequestFactory().get("/")
        request.user = self.admin_user
        self.assertNotIn("delete_selected", self._admin().get_actions(request))
