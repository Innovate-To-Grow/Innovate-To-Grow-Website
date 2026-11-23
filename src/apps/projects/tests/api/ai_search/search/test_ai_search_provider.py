"""Past-project AI search on an API-key provider: available with a usable provider and no AWS, unavailable when the
provider is disabled or keyless, ``<preset>/<model>`` in the audit log, and the provider passed to the model call."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.projects.models import Semester
from apps.projects.services.ai_search import run_past_project_ai_search
from apps.system_intelligence.models import AssistantMessageLog, SystemIntelligenceConfig
from apps.system_intelligence.services.bedrock import BedrockError
from apps.system_intelligence.tests.services.agents.provider_runtime.helpers import ProviderStoreMixin, make_provider

from ..helpers.ai_search_helpers import SEARCH_URL, SERVICE_AGENT, VIEW_SEARCH, Member, agent_result, create_project


class _ProviderSearchCase(ProviderStoreMixin, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        self.member = Member.objects.create_user(email="member@example.com", password="pw", is_active=True)
        self.provider = make_provider()
        # No AWSCredentialConfig row: the provider route must not need one.
        self.config = SystemIntelligenceConfig.objects.create(
            name="AI",
            is_active=True,
            public_assistant_provider=self.provider,
            public_assistant_model_id="deepseek-chat",
            public_assistant_ip_token_limit=100_000,
            public_assistant_ip_token_window_seconds=3600,
        )
        current = Semester.objects.create(year=2025, season=Semester.Season.FALL, is_published=True)
        past = Semester.objects.create(year=2024, season=Semester.Season.FALL, is_published=True)
        create_project(current, project_title="Current Solar Project")
        self.project = create_project(past, project_title="Solar Sensor Irrigation Network")


class AISearchEndpointProviderTests(_ProviderSearchCase):
    def _post_unavailable(self):
        with self.assertLogs("apps.projects.views.ai_search", level="WARNING"):
            return self._post()

    def _post(self):
        self.client.force_authenticate(user=self.member)
        outcome = {
            "project_ids": [str(self.project.id)],
            "usage": {"inputTokens": 5, "outputTokens": 2, "totalTokens": 7},
        }
        with patch(VIEW_SEARCH, return_value=outcome) as search:
            response = self.client.post(SEARCH_URL, {"query": "solar"}, format="json")
        return response, search

    def test_available_with_provider_and_no_aws(self):
        self.assertFalse(AWSCredentialConfig.load().is_configured)
        response, search = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual([p["project_title"] for p in response.data["results"]], ["Solar Sensor Irrigation Network"])
        search.assert_called_once()
        log = AssistantMessageLog.objects.get()
        self.assertEqual(log.model_id, "deepseek/deepseek-chat")
        self.assertEqual(log.status, AssistantMessageLog.STATUS_OK)

    def test_disabled_provider_reports_unavailable(self):
        self.provider.is_enabled = False
        self.provider.save()
        response, search = self._post_unavailable()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        search.assert_not_called()
        log = AssistantMessageLog.objects.get()
        self.assertEqual(log.status, AssistantMessageLog.STATUS_UNAVAILABLE)
        self.assertEqual(log.model_id, "deepseek/deepseek-chat")

    def test_keyless_provider_reports_unavailable(self):
        keyless = make_provider(name="Kimi", preset="moonshot_cn", with_key=False, enabled=False)
        keyless.is_enabled = True  # enabled without a key (bypassing clean): still never called
        keyless.save()
        self.config.public_assistant_provider = keyless
        self.config.public_assistant_model_id = "kimi-latest"
        self.config.save()
        response, search = self._post_unavailable()
        self.assertFalse(response.data["available"])
        search.assert_not_called()
        self.assertEqual(AssistantMessageLog.objects.get().model_id, "moonshot_cn/kimi-latest")


class AISearchServiceProviderTests(_ProviderSearchCase):
    def test_model_call_receives_the_public_provider(self):
        with patch(SERVICE_AGENT, return_value=agent_result(self.project)) as agent:
            outcome = run_past_project_ai_search(query="solar", limit=5, config=self.config)
        self.assertEqual(outcome["project_ids"], [str(self.project.id)])
        self.assertEqual(agent.call_args.kwargs["provider"], self.provider)
        self.assertEqual(agent.call_args.kwargs["model_id"], "deepseek-chat")

    def test_temperature_retry_keeps_the_provider(self):
        with patch(SERVICE_AGENT, side_effect=[Exception("Invalid temperature"), agent_result(self.project)]) as agent:
            run_past_project_ai_search(query="solar", limit=5, config=self.config)
        first, second = agent.call_args_list
        self.assertEqual(first.kwargs["provider"], self.provider)
        self.assertEqual(second.kwargs["provider"], self.provider)
        self.assertFalse(second.kwargs["include_temperature"])

    def test_failed_retry_raises_bedrock_error(self):
        effects = [Exception("Invalid temperature"), RuntimeError("still failing")]
        with patch(SERVICE_AGENT, side_effect=effects), self.assertRaises(BedrockError):
            run_past_project_ai_search(query="solar", limit=5, config=self.config)
