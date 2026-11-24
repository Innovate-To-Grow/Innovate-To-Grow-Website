"""The scam AI second opinion on System Intelligence's default route: an API-key provider goes through the tool-free
agent (with one temperature retry), a disabled or keyless provider skips the review, Bedrock still uses
``invoke_bedrock``."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.models import AWSCredentialConfig
from apps.mail.services.scam_detector.llm_classifier import llm_review
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.tests.services.agents.provider_runtime.helpers import ProviderStoreMixin, make_provider

_MODULE = "apps.mail.services.scam_detector.llm_classifier"
_AGENT_PATH = f"{_MODULE}.run_tool_free_agent"
_BEDROCK_PATH = f"{_MODULE}.invoke_bedrock"
_VERDICT = '{"verdict": "scam", "confidence": 0.8, "risk_score": 90, "reasons": ["lookalike domain"]}'


def _msg():
    return {"uid": "1", "from_email": "a@example.com", "subject": "Verify now", "text": "click", "html": ""}


class LlmReviewProviderTests(ProviderStoreMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.provider = make_provider()
        # No AWSCredentialConfig: the provider route must not need one.
        self.config = SystemIntelligenceConfig.objects.create(
            name="SI", is_active=True, default_provider=self.provider, default_model_id="deepseek-chat"
        )

    def test_provider_path_calls_tool_free_agent_with_provider(self):
        with patch(_AGENT_PATH, return_value=MagicMock(text=_VERDICT)) as agent, patch(_BEDROCK_PATH) as bedrock:
            review = llm_review(_msg())
        self.assertEqual(review["verdict"], "scam")
        self.assertEqual(review["reasons"], ["lookalike domain"])
        bedrock.assert_not_called()
        kwargs = agent.call_args.kwargs
        self.assertEqual(kwargs["provider"], self.provider)
        self.assertEqual(kwargs["model_id"], "deepseek-chat")
        self.assertEqual(kwargs["temperature"], 0.0)
        self.assertEqual(kwargs["max_tokens"], 512)
        self.assertEqual(kwargs["agent_name"], "mail_scam_review")
        self.assertIn("Subject: Verify now", kwargs["input_data"])
        self.assertNotIn("include_temperature", kwargs)

    def test_temperature_rejection_is_retried_once_without_temperature(self):
        effects = [Exception("Invalid temperature: only 1 is allowed for this model"), MagicMock(text=_VERDICT)]
        with patch(_AGENT_PATH, side_effect=effects) as agent:
            review = llm_review(_msg())
        self.assertEqual(review["verdict"], "scam")
        self.assertEqual(agent.call_count, 2)
        self.assertFalse(agent.call_args_list[1].kwargs["include_temperature"])
        self.assertEqual(agent.call_args_list[1].kwargs["provider"], self.provider)

    def test_other_provider_errors_fall_back_to_rules(self):
        with patch(_AGENT_PATH, side_effect=RuntimeError("boom")) as agent:
            with self.assertLogs(_MODULE, level="WARNING"):
                self.assertIsNone(llm_review(_msg()))
        agent.assert_called_once()

    def test_disabled_provider_skips_the_review(self):
        self.provider.is_enabled = False
        self.provider.save()
        with patch(_AGENT_PATH) as agent, patch(_BEDROCK_PATH) as bedrock:
            self.assertIsNone(llm_review(_msg()))
        agent.assert_not_called()
        bedrock.assert_not_called()

    def test_keyless_provider_skips_the_review(self):
        keyless = make_provider(name="Kimi", preset="moonshot", with_key=False, enabled=False)
        keyless.is_enabled = True
        keyless.save()
        self.config.default_provider = keyless
        self.config.save()
        with patch(_AGENT_PATH) as agent:
            self.assertIsNone(llm_review(_msg()))
        agent.assert_not_called()


class LlmReviewBedrockRouteTests(TestCase):
    def test_bedrock_route_still_uses_invoke_bedrock(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="test",
            secret_access_key="test",
            default_region="us-west-2",
        )
        SystemIntelligenceConfig.objects.create(name="SI", is_active=True)
        with patch(_BEDROCK_PATH, return_value={"text": _VERDICT}) as bedrock, patch(_AGENT_PATH) as agent:
            review = llm_review(_msg())
        self.assertEqual(review["verdict"], "scam")
        bedrock.assert_called_once()
        agent.assert_not_called()
        self.assertEqual(bedrock.call_args.kwargs["chat_config"].temperature, 0.0)
