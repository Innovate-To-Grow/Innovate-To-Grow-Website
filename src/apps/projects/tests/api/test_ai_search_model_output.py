"""AI search survives whatever the model returns, and members never see operator-facing text."""

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.projects.models import Semester
from apps.system_intelligence.models import AssistantMessageLog, SystemIntelligenceConfig

from .ai_search_helpers import SEARCH_URL, SERVICE_AGENT, Member, create_project


class AISearchModelOutputTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(user=Member.objects.create_user(email="member@example.com", password="pw"))
        self.config = SystemIntelligenceConfig.objects.create(
            name="AI",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            public_assistant_ip_token_limit=100_000,
            public_assistant_ip_token_window_seconds=3600,
        )
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKIATEST", secret_access_key="secret", default_region="us-west-2"
        )
        semester = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_published=True)
        self.candidate = create_project(semester, project_title="Solar Sensor Irrigation Network")
        # Published, but no word of the query matches it, so it is never a candidate.
        self.non_candidate = create_project(
            semester, project_title="Water Quality Lab", team_name="Lab", abstract="", organization="City"
        )

    def _search(self, reply_text):
        reply = MagicMock(text=reply_text, usage={"totalTokens": 9})
        with patch(SERVICE_AGENT, return_value=reply):
            return self.client.post(SEARCH_URL, {"query": "solar"}, format="json")

    def _titles(self, response):
        return [project["project_title"] for project in response.data["results"]]

    def test_ids_that_are_not_uuids_are_dropped_and_the_turn_is_logged(self):
        for reply_text in ('{"ids": ["project-id"]}', '{"ids": [1, {"id": 2}]}', '{"ids": ["<candidate UUID>"]}'):
            with self.subTest(reply_text=reply_text):
                AssistantMessageLog.objects.all().delete()

                response = self._search(reply_text)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["results"], [])
                self.assertEqual(AssistantMessageLog.objects.get().status, AssistantMessageLog.STATUS_OK)

    def test_an_echoed_id_prefix_is_read_as_the_id(self):
        response = self._search(f'{{"ids": ["id={self.candidate.id}"]}}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._titles(response), ["Solar Sensor Irrigation Network"])

    def test_ids_outside_the_candidates_are_dropped(self):
        response = self._search(f'{{"ids": ["{self.non_candidate.id}", "{str(self.candidate.id).upper()}"]}}')

        self.assertEqual(self._titles(response), ["Solar Sensor Irrigation Network"])

    def test_a_failed_results_lookup_is_still_logged(self):
        with patch("apps.projects.views.ai_search.ai_search_results", side_effect=RuntimeError("db down")):
            response = self._search(f'{{"ids": ["{self.candidate.id}"]}}')

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "ai_search_error")
        self.assertEqual(AssistantMessageLog.objects.get().status, AssistantMessageLog.STATUS_ERROR)

    def test_unconfigured_ai_search_tells_members_without_operator_detail(self):
        AWSCredentialConfig.objects.all().delete()

        with self.assertLogs("apps.projects.views.ai_search", level="WARNING") as logs:
            response = self.client.post(SEARCH_URL, {"query": "solar"}, format="json")

        self.assertFalse(response.data["available"])
        self.assertNotIn("Bedrock", response.data["message"])
        self.assertNotIn("AWS", response.data["message"])
        self.assertIn("Bedrock", "\n".join(logs.output))
