from unittest.mock import MagicMock, patch

from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.projects.tests.api.ai_search.test_ai_search_scope import ALL_PROMPT, TABLE_FIELDS, AISearchScopeTestCase
from apps.system_intelligence.models import AssistantMessageLog

from .ai_search_helpers import SEARCH_URL, SERVICE_AGENT, VIEW_SEARCH, Member


class AISearchScopeEndpointTests(AISearchScopeTestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKIATEST", secret_access_key="secret", default_region="us-west-2"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=Member.objects.create_user(email="member@example.com", password="pw"))

    def search(self, ids, **payload):
        outcome = {"project_ids": [str(project_id) for project_id in ids], "usage": {"totalTokens": 9}}
        with patch(VIEW_SEARCH, return_value=outcome):
            return self.client.post(SEARCH_URL, {"query": "solar", **payload}, format="json")

    def test_an_unknown_scope_is_a_400(self):
        response = self.client.post(SEARCH_URL, {"query": "solar", "scope": "everything"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("scope", response.data)

    def test_all_scope_ranks_and_returns_current_projects(self):
        kiln = self.current["10"]
        reply = MagicMock(text=f'{{"ids": ["{kiln.pk}", "{self.sensor.pk}"]}}', usage={"totalTokens": 9})

        with patch(SERVICE_AGENT, return_value=reply) as agent:
            response = self.client.post(SEARCH_URL, {"query": "solar", "scope": "all"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(agent.call_args.kwargs["input_data"].startswith(ALL_PROMPT))
        current, archived = response.data["results"]
        self.assertEqual(
            current,
            {
                "id": str(kiln.pk),
                "semester_label": "2026-2 Fall",
                "class_code": "CAP",
                "team_number": "10",
                "team_name": "",
                "project_title": "Kiln",
                "organization": "",
                "industry": "",
                "abstract": "Dries lumber with solar heat.",
                "student_names": "Ada Lovelace",
                "track": 1,
                "presentation_order": 1,
                "catalog": "current",
                "is_presenting": True,
            },
        )
        self.assertEqual(set(archived), TABLE_FIELDS | {"catalog", "is_presenting"})
        self.assertEqual(
            (archived["id"], archived["catalog"], archived["is_presenting"]), (str(self.sensor.pk), "archive", None)
        )
        self.assertEqual(
            AssistantMessageLog.objects.get().results,
            [
                {"id": str(kiln.pk), "project_title": "Kiln"},
                {"id": str(self.sensor.pk), "project_title": "Solar Sensor Platform"},
            ],
        )

    def test_past_scope_returns_archive_rows_with_their_catalog_fields_only(self):
        response = self.search([self.current["10"].pk, self.sensor.pk])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(row["id"], row["catalog"], row["is_presenting"]) for row in response.data["results"]],
            [(str(self.sensor.pk), "archive", None)],
        )

    def test_all_scope_returns_each_project_once_as_the_archive_holds_it(self):
        response = self.search(
            [self.current["9"].pk, self.seed_counter.pk, self.current["10"].pk, self.current["10"].pk], scope="all"
        )

        self.assertEqual(
            [(row["id"], row["catalog"]) for row in response.data["results"]],
            [(str(self.seed_counter.pk), "archive"), (str(self.current["10"].pk), "current")],
        )
