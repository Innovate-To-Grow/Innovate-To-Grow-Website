"""AI search's scope: "past" ranks the archive as before, "all" ranks what /projects/all/ lists."""

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import AWSCredentialConfig
from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.event.services import sync_schedule
from apps.projects.models import Project, Semester
from apps.projects.serializers import PastProjectAISearchSerializer
from apps.projects.services.ai_search import (
    SCOPE_ALL,
    SCOPE_PAST,
    find_ai_search_candidates,
    prepare_past_project_ai_search,
)
from apps.system_intelligence.models import AssistantMessageLog, SystemIntelligenceConfig

from .ai_search_helpers import SEARCH_URL, SERVICE_AGENT, VIEW_SEARCH, Member, create_project

TABLE_FIELDS = {
    "id",
    "semester_label",
    "class_code",
    "team_number",
    "team_name",
    "project_title",
    "organization",
    "industry",
    "abstract",
    "student_names",
    "track",
    "presentation_order",
}
PAST_PROMPT = "Choose the past Innovate to Grow projects that best match the user's search query.\n"
ALL_PROMPT = (
    "Choose the Innovate to Grow projects, this semester's and past ones, that best match the user's search query.\n"
)


def _slotted(order, team, title, **extra):
    return {
        "Track": 1,
        "Order": order,
        "Year-Semester": "2026-2 Fall",
        "Class": "CAP",
        "Team#": team,
        "Project Title": title,
        **extra,
    }


class AISearchScopeTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.config = SystemIntelligenceConfig.objects.create(
            name="AI",
            is_active=True,
            default_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            public_assistant_ip_token_limit=100_000,
            public_assistant_ip_token_window_seconds=3600,
        )
        spring = CurrentProjectSchedule.objects.create(name="2026 Spring I2G Event")
        sync_schedule(
            spring,
            tracks_records=[{"Track": 1, "Room": "Granite", "Class": "CAP"}],
            projects_records=[{**_slotted(1, "50", "Solar Spring Robot"), "Year-Semester": "2026-1 Spring"}],
        )
        self.schedule = CurrentProjectSchedule.objects.create(name="2026 Fall I2G Event", is_active=True)
        sync_schedule(
            self.schedule,
            tracks_records=[{"Track": 1, "Room": "Granite", "Class": "CAP"}],
            projects_records=[
                _slotted(
                    1, "10", "Kiln", Abstract="Dries lumber with solar heat.", **{"Student Names": "Ada Lovelace"}
                ),
                _slotted(2, "9", "Seed Counter", Abstract="Counts seeds with a solar camera."),
                _slotted(3, "11", "Course Planner"),
            ],
        )
        self.current = {project.team_number: project for project in CurrentProject.objects.filter(schedule=spring)}
        self.current.update(
            {project.team_number: project for project in CurrentProject.objects.filter(schedule=self.schedule)}
        )
        fall = Semester.objects.create(year=2026, season=Semester.Season.FALL, is_published=True)
        old = Semester.objects.create(year=2025, season=Semester.Season.FALL, is_published=True)
        # The archive already holds fall's CAP 9, so it is offered once, as this project.
        self.seed_counter = create_project(fall, class_code="CAP", team_number="9", project_title="Seed Counter")
        self.sensor = create_project(old, project_title="Solar Sensor Platform")

    def candidate_ids(self, query, **kwargs):
        return [candidate.id for candidate in find_ai_search_candidates(query, **kwargs)]


class AISearchScopeCandidateTests(AISearchScopeTestCase):
    def test_past_scope_offers_the_archive_only(self):
        expected = [str(self.seed_counter.pk), str(self.sensor.pk)]

        self.assertEqual(self.candidate_ids("solar"), expected)
        self.assertEqual(self.candidate_ids("solar", scope=SCOPE_PAST), expected)

    def test_all_scope_offers_the_active_schedules_unarchived_projects_first(self):
        candidates = find_ai_search_candidates("solar", scope=SCOPE_ALL)

        self.assertEqual(
            [(candidate.id, candidate.semester_label) for candidate in candidates],
            [
                (str(self.current["10"].pk), "2026-2 Fall"),
                (str(self.seed_counter.pk), "2026-2 Fall"),
                (str(self.sensor.pk), "2025-2 Fall"),
            ],
        )
        self.assertEqual(candidates[0].abstract, "Dries lumber with solar heat.")

    def test_all_scope_reads_a_current_projects_abstract_and_student_names(self):
        self.assertEqual(self.candidate_ids("lumber", scope=SCOPE_ALL), [str(self.current["10"].pk)])
        self.assertEqual(self.candidate_ids("LOVELACE", scope=SCOPE_ALL), [str(self.current["10"].pk)])

    def test_all_scope_offers_at_most_20_current_projects_and_80_in_all(self):
        CurrentProject.objects.bulk_create(
            CurrentProject(schedule=self.schedule, class_code="ENG", team_number=str(n), project_title=f"Solar {n}")
            for n in range(1, 31)
        )
        Project.objects.bulk_create(
            Project(semester=self.sensor.semester, class_code="ENG", team_number=str(n), project_title=f"Solar {n}")
            for n in range(1, 101)
        )
        current_ids = {str(pk) for pk in CurrentProject.objects.values_list("pk", flat=True)}

        ids = self.candidate_ids("solar", scope=SCOPE_ALL)

        self.assertEqual(len(ids), 80)
        self.assertEqual([project_id in current_ids for project_id in ids], [True] * 20 + [False] * 60)

    def test_all_scope_without_an_active_schedule_offers_what_past_does(self):
        CurrentProjectSchedule.objects.update(is_active=False)

        self.assertEqual(self.candidate_ids("solar", scope=SCOPE_ALL), self.candidate_ids("solar"))

    def test_the_prompt_names_the_scope(self):
        past = prepare_past_project_ai_search(query="solar", limit=5, config=self.config)
        everything = prepare_past_project_ai_search(query="solar", limit=5, config=self.config, scope=SCOPE_ALL)

        self.assertTrue(past.prompt.startswith(PAST_PROMPT))
        self.assertNotIn(str(self.current["10"].pk), past.prompt)
        self.assertTrue(everything.prompt.startswith(ALL_PROMPT))
        self.assertIn(f"id={self.current['10'].pk} | title=Kiln | semester=2026-2 Fall", everything.prompt)
        self.assertEqual(
            everything.candidate_ids, {str(self.current["10"].pk), str(self.seed_counter.pk), str(self.sensor.pk)}
        )

    def test_scope_defaults_to_past(self):
        serializer = PastProjectAISearchSerializer(data={"query": "solar"})

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["scope"], SCOPE_PAST)


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
