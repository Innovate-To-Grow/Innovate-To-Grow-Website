"""The past-projects AI search endpoint and its preparation step."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.projects.models import Semester
from apps.system_intelligence.models import (
    AssistantMessageLog,
    SystemIntelligenceConfig,
)
from apps.system_intelligence.services.public_assistant import (
    member_actor,
    record_usage,
)

from .ai_search_helpers import BUDGET_MESSAGE, Member, create_project


class _PastProjectAISearchAPIViewCase(TestCase):
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


class PastProjectAISearchAPIViewTests(_PastProjectAISearchAPIViewCase):
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
