from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase

from apps.projects.models import Semester
from apps.projects.services.ai_search import (
    PreparedPastProjectAISearch,
    prepare_past_project_ai_search,
    run_past_project_ai_search,
)
from apps.system_intelligence.models import (
    SystemIntelligenceConfig,
)

from ..helpers.ai_search_helpers import SERVICE_AGENT, agent_result, create_project


class PreparePastProjectAISearchTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.config = SystemIntelligenceConfig.objects.create(
            name="AI",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        semester = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_published=True)
        self.project = create_project(semester, project_title="Solar Sensor Irrigation Network")

    def test_prepare_returns_none_without_candidates(self):
        self.assertIsNone(prepare_past_project_ai_search(query="zzzzzz", limit=5, config=self.config))

    def test_prepare_estimates_the_whole_prompt_and_caps_output(self):
        prepared = prepare_past_project_ai_search(query="solar", limit=50, config=self.config)

        self.assertEqual(prepared.limit, 10)
        self.assertIn(str(self.project.id), prepared.prompt)
        self.assertEqual(prepared.max_tokens, 700)
        # At least the 4-characters-per-token floor over system text + prompt.
        self.assertGreaterEqual(
            prepared.estimated_input_tokens,
            (len(prepared.system_text) + len(prepared.prompt)) // 4,
        )

    def test_estimate_charges_non_ascii_text_conservatively(self):
        ascii_only = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)
        self.project.abstract = "太阳能传感器网络" * 20
        self.project.save()

        with_cjk = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)

        # 160 CJK characters are 480 UTF-8 bytes: charged one token per byte.
        self.assertGreater(with_cjk.estimated_input_tokens, ascii_only.estimated_input_tokens + 400)

    def test_prepare_offers_its_candidates_and_a_prepared_search_must_name_them(self):
        prepared = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)

        self.assertEqual(prepared.candidate_ids, frozenset({str(self.project.id)}))
        # An empty candidate set selects nothing, so leaving the ids out is an error, not a search without results.
        with self.assertRaises(TypeError):
            PreparedPastProjectAISearch(limit=5, system_text="", prompt="", max_tokens=1, estimated_input_tokens=1)

    def test_output_cap_follows_a_smaller_configured_response_limit(self):
        self.config.public_assistant_max_response_tokens = 200

        prepared = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)

        self.assertEqual(prepared.max_tokens, 200)

    def test_run_reuses_a_prepared_prompt_without_searching_again(self):
        prepared = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)
        result = MagicMock(text=f'{{"ids": ["{self.project.id}"]}}', usage={"totalTokens": 9})

        with (
            patch(SERVICE_AGENT, return_value=result) as mock_agent,
            patch("apps.projects.services.ai_search.search.find_ai_search_candidates") as mock_candidates,
        ):
            outcome = run_past_project_ai_search(query="solar", limit=5, config=self.config, prepared=prepared)

        mock_candidates.assert_not_called()
        self.assertEqual(outcome["project_ids"], [str(self.project.id)])
        self.assertEqual(mock_agent.call_args.kwargs["input_data"], prepared.prompt)
        self.assertEqual(mock_agent.call_args.kwargs["system_text"], prepared.system_text)
        self.assertEqual(mock_agent.call_args.kwargs["max_tokens"], prepared.max_tokens)

    def test_run_without_candidates_returns_empty_without_a_model_call(self):
        with patch(SERVICE_AGENT, return_value=agent_result(self.project)) as mock_agent:
            outcome = run_past_project_ai_search(query="zzzzzz", limit=5, config=self.config)

        mock_agent.assert_not_called()
        self.assertEqual(outcome, {"project_ids": [], "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}})
