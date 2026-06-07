from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.projects.models import Project, Semester
from apps.projects.services.ai_search import find_ai_search_candidates
from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import hash_ip, record_usage

Member = get_user_model()


def create_project(semester, **overrides):
    defaults = {
        "project_title": "Solar Sensor Platform",
        "team_number": "101",
        "class_code": "CAP",
        "team_name": "Solar Sensors",
        "organization": "Irrigation District",
        "industry": "Agriculture",
        "abstract": "A solar-powered sensor network for field monitoring.",
        "student_names": "Alex Student",
    }
    defaults.update(overrides)
    return Project.objects.create(semester=semester, **defaults)


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
            public_assistant_ip_token_limit=1000,
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
        self.config.public_assistant_ip_token_limit = 1
        self.config.save()
        record_usage(hash_ip("127.0.0.1"), 1, 3600)

        with patch("apps.projects.views.ai_search.run_past_project_ai_search") as mocked_search:
            response = self.client.post("/projects/past-ai-search/", {"query": "solar"}, format="json")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "budget_exceeded")
        mocked_search.assert_not_called()

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
        self.assertEqual(
            [project["project_title"] for project in response.data["results"]],
            ["Battery Health Monitor", "Solar Sensor Irrigation Network"],
        )

    def test_candidate_search_uses_past_project_boundary(self):
        candidates = find_ai_search_candidates("solar")
        titles = {project.project_title for project in candidates}

        self.assertIn("Solar Sensor Irrigation Network", titles)
        self.assertIn("Battery Health Monitor", titles)
        self.assertNotIn("Current Solar Project", titles)
        self.assertNotIn("Unpublished Solar Project", titles)

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
