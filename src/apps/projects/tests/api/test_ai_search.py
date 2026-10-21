"""The past-projects AI search endpoint and its preparation step."""

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.projects.models import Semester
from apps.projects.services.ai_search import (
    find_ai_search_candidates,
    prepare_past_project_ai_search,
    run_past_project_ai_search,
)
from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import (
    member_actor,
    record_usage,
)

from .ai_search_helpers import (
    BUDGET_MESSAGE,
    SERVICE_AGENT,
    Member,
    agent_result,
    create_project,
)


class PastProjectAISearchAPIViewTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.member = Member.objects.create_user(email="member@example.com", password="pw")

        self.config = SystemIntelligenceConfig.objects.create(
            name="AI",
            is_active=True,
            public_assistant_enabled=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            public_assistant_max_message_chars=100,
            public_assistant_ip_token_limit=100_000,
            public_assistant_ip_token_window_seconds=3600,
        )
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKIATEST",
            secret_access_key="secret",
            default_region="us-west-2",
        )

        self.current = Semester.objects.create(year=2025, season=Semester.Season.FALL, is_published=True)
        self.past_spring = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_published=True)
        self.past_fall = Semester.objects.create(year=2024, season=Semester.Season.FALL, is_published=True)
        self.unpublished = Semester.objects.create(year=2024, season=Semester.Season.SPRING, is_published=False)

        self.current_project = create_project(self.current, project_title="Current Solar Project")
        self.past_project_a = create_project(
            self.past_spring,
            project_title="Solar Sensor Irrigation Network",
            team_number="101",
        )
        self.past_project_b = create_project(
            self.past_fall,
            project_title="Battery Health Monitor",
            team_number="102",
            abstract="Predictive maintenance for solar battery systems.",
        )
        self.unpublished_project = create_project(self.unpublished, project_title="Unpublished Solar Project")

    def authenticate(self):
        self.client.force_authenticate(user=self.member)

    def test_authentication_required(self):
        response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 401)

    def test_blank_query_validation(self):
        self.authenticate()

        response = self.client.post("/projects/past-ai-search/", {"query": "   "}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("query", response.data)

    def test_too_long_query_validation(self):
        self.authenticate()
        self.config.public_assistant_max_message_chars = 5
        self.config.save()

        response = self.client.post("/projects/past-ai-search/", {"query": "too long"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("query", response.data)

    def test_public_assistant_disabled_does_not_disable_ai_search(self):
        self.authenticate()
        self.config.public_assistant_enabled = False
        self.config.save()

        with patch(
            "apps.projects.views.ai_search.run_past_project_ai_search",
            return_value={
                "project_ids": [str(self.past_project_a.id)],
                "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": 13},
            },
        ) as mocked_search:
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(
            [project["project_title"] for project in response.data["results"]], ["Solar Sensor Irrigation Network"]
        )
        mocked_search.assert_called_once()

    def test_budget_limit_returns_429_without_calling_ai(self):
        self.authenticate()
        self.config.public_assistant_ip_token_limit = 5000
        self.config.save()
        record_usage(member_actor(self.member.pk).key, 5000, 3600)

        # A real return value: if the budget check regressed, the test must fail
        # on the assertions below, not hang serialising a MagicMock.
        with patch(
            "apps.projects.views.ai_search.run_past_project_ai_search",
            return_value={"project_ids": [], "usage": {"totalTokens": 1}},
        ) as mocked_search:
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "budget_exceeded")
        # The limit may be the shared global one, so the copy must not blame the member.
        self.assertEqual(response.data["detail"], BUDGET_MESSAGE)
        mocked_search.assert_not_called()
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_BUDGET)

    def test_ai_project_ids_return_serialized_projects_in_ai_order(self):
        self.authenticate()
        invalid_id = "00000000-0000-0000-0000-000000000000"

        with patch(
            "apps.projects.views.ai_search.run_past_project_ai_search",
            return_value={
                "project_ids": [
                    str(self.past_project_b.id),
                    str(self.current_project.id),
                    invalid_id,
                    str(self.unpublished_project.id),
                    str(self.past_project_a.id),
                ],
                "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": 13},
            },
        ):
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(response.data["query"], "solar")
        self.assertEqual(response.data["usage"]["totalTokens"], 13)
        # The newest published semester is included now, so the current project is serialized too
        # (in AI order); only the invalid id and the unpublished project are dropped.
        self.assertEqual(
            [project["project_title"] for project in response.data["results"]],
            ["Battery Health Monitor", "Current Solar Project", "Solar Sensor Irrigation Network"],
        )

    def test_candidate_search_uses_past_project_boundary(self):
        candidates = find_ai_search_candidates("solar")
        titles = {project.project_title for project in candidates}

        self.assertIn("Solar Sensor Irrigation Network", titles)
        self.assertIn("Battery Health Monitor", titles)
        # Every published semester is in scope, including the newest; only unpublished is excluded.
        self.assertIn("Current Solar Project", titles)
        self.assertNotIn("Unpublished Solar Project", titles)

    def test_service_uses_tool_free_agent_and_parses_ids(self):
        result = MagicMock(
            text=f'{{"ids": ["{self.past_project_b.id}", "{self.past_project_a.id}"], "reason": "solar"}}',
            usage={"inputTokens": 8, "outputTokens": 4, "totalTokens": 12},
        )

        with patch("apps.projects.services.ai_search.run_tool_free_agent", return_value=result) as mock_agent:
            outcome = run_past_project_ai_search(query="solar", limit=2, config=self.config)

        self.assertEqual(outcome["project_ids"], [str(self.past_project_b.id), str(self.past_project_a.id)])
        self.assertEqual(outcome["usage"]["totalTokens"], 12)
        mock_agent.assert_called_once()
        self.assertEqual(mock_agent.call_args.kwargs["agent_name"], "past_project_ai_search")

    def test_success_logs_source_user_and_results(self):
        self.authenticate()
        with patch(
            "apps.projects.views.ai_search.run_past_project_ai_search",
            return_value={
                "project_ids": [str(self.past_project_a.id)],
                "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": 13},
            },
        ):
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 200)
        message = AssistantMessageLog.objects.get()
        convo = message.conversation
        self.assertEqual(convo.source, AssistantConversationLog.SOURCE_AI_SEARCH)
        self.assertEqual(convo.user_id, self.member.id)
        self.assertIsNone(convo.session_id)
        self.assertEqual(message.status, AssistantMessageLog.STATUS_OK)
        self.assertEqual(message.prompt, "solar")
        self.assertEqual(
            message.results,
            [{"id": str(self.past_project_a.id), "project_title": "Solar Sensor Irrigation Network"}],
        )

    def test_unavailable_logs_unavailable_row(self):
        self.authenticate()
        self.config.default_model_id = ""
        self.config.public_assistant_model_id = ""
        self.config.save()

        response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_UNAVAILABLE)
        self.assertEqual(message.conversation.user_id, self.member.id)

    def test_error_logs_error_row(self):
        self.authenticate()
        with patch(
            "apps.projects.views.ai_search.run_past_project_ai_search",
            side_effect=RuntimeError("boom"),
        ):
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 502)
        message = AssistantMessageLog.objects.get()
        self.assertEqual(message.status, AssistantMessageLog.STATUS_ERROR)

    def test_recorder_failure_does_not_break_response(self):
        self.authenticate()
        with (
            patch(
                "apps.projects.views.ai_search.run_past_project_ai_search",
                return_value={
                    "project_ids": [str(self.past_project_a.id)],
                    "usage": {"inputTokens": 10, "outputTokens": 3, "totalTokens": 13},
                },
            ),
            patch(
                "apps.system_intelligence.services.usage_log.recorder.AssistantMessageLog.objects.create",
                side_effect=RuntimeError("audit down"),
            ),
        ):
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(AssistantMessageLog.objects.count(), 0)


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

    def test_output_cap_follows_a_smaller_configured_response_limit(self):
        self.config.public_assistant_max_response_tokens = 200

        prepared = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)

        self.assertEqual(prepared.max_tokens, 200)

    def test_run_reuses_a_prepared_prompt_without_searching_again(self):
        prepared = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)
        result = MagicMock(text=f'{{"ids": ["{self.project.id}"]}}', usage={"totalTokens": 9})

        with (
            patch(SERVICE_AGENT, return_value=result) as mock_agent,
            patch("apps.projects.services.ai_search.find_ai_search_candidates") as mock_candidates,
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
