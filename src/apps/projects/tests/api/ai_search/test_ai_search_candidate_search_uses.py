from unittest.mock import MagicMock, patch

from apps.projects.services.ai_search import (
    find_ai_search_candidates,
    run_past_project_ai_search,
)
from apps.projects.tests.api.ai_search.test_ai_search import _PastProjectAISearchAPIViewCase
from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
)


class PastProjectAISearchAPIViewTests(_PastProjectAISearchAPIViewCase):
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

        with patch("apps.projects.services.ai_search.search.run_tool_free_agent", return_value=result) as mock_agent:
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
