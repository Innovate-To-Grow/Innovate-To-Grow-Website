from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.projects.models import Project, Semester


class CompactPastProjectsAPIViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.fall = Semester.objects.create(year=2025, season=2, is_published=True)
        self.spring = Semester.objects.create(year=2025, season=1, is_published=True)
        self.old = Semester.objects.create(year=2024, season=2, is_published=True)
        self.hidden = Semester.objects.create(year=2026, season=1, is_published=False)
        self.alpha = self.create_project(
            self.fall,
            "Solar Analytics",
            class_code="CAP",
            team_number="2",
            organization="Acme Energy",
            abstract="Forecast renewable output",
        )
        self.beta = self.create_project(
            self.fall,
            "Water Monitor",
            class_code="CAP",
            team_number="10",
            student_names="Searchable Student",
        )
        self.spring_project = self.create_project(self.spring, "Spring Robotics", class_code="ME", team_number="1")
        self.old_project = self.create_project(self.old, "Old Project", class_code="CSE", team_number="3")
        self.create_project(self.hidden, "Unpublished Project")

    @staticmethod
    def create_project(semester, title, **kwargs):
        return Project.objects.create(semester=semester, project_title=title, **kwargs)

    def test_paginates_compact_rows_with_stable_ordering(self):
        response = self.client.get("/projects/archive/", {"page": 1, "page_size": 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 4)
        self.assertEqual([row["id"] for row in response.data["results"]], [str(self.beta.id), str(self.alpha.id)])
        self.assertEqual(
            set(response.data["results"][0]),
            {
                "id",
                "semester_label",
                "class_code",
                "team_number",
                "team_name",
                "project_title",
                "organization",
                "industry",
                "track",
                "presentation_order",
            },
        )
        self.assertNotIn("abstract", response.data["results"][0])
        second = self.client.get("/projects/archive/", {"page": 2, "page_size": 2})
        self.assertEqual(
            [row["id"] for row in second.data["results"]], [str(self.spring_project.id), str(self.old_project.id)]
        )

    def test_searches_text_fields_case_insensitively(self):
        for search in ("solar", "ACME", "renewable", "searchable student"):
            with self.subTest(search=search):
                response = self.client.get("/projects/archive/", {"search": search})
                self.assertEqual(response.data["count"], 1)

    def test_filters_by_year_season_and_semester_label(self):
        response = self.client.get("/projects/archive/", {"year": 2025, "season": 1})
        self.assertEqual([row["project_title"] for row in response.data["results"]], ["Spring Robotics"])

        response = self.client.get("/projects/archive/", {"semester": "2024-2 fall"})
        self.assertEqual([row["project_title"] for row in response.data["results"]], ["Old Project"])

    def test_rejects_invalid_pagination_and_filters(self):
        for params in (
            {"page": 0},
            {"page": "nope"},
            {"page_size": 0},
            {"page_size": 101},
            {"year": 1999},
            {"season": 3},
            {"semester": ""},
        ):
            with self.subTest(params=params):
                response = self.client.get("/projects/archive/", params)
                self.assertEqual(response.status_code, 400)

    def test_excludes_unpublished_and_uses_select_related(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/projects/archive/", {"page_size": 100})
        self.assertNotIn("Unpublished Project", [row["project_title"] for row in response.data["results"]])
        self.assertLessEqual(len(queries), 2)

    def test_returns_query_specific_public_etag_and_supports_conditional_get(self):
        first = self.client.get("/projects/archive/", {"page_size": 2})
        other_query = self.client.get("/projects/archive/", {"page_size": 1})

        self.assertEqual(first["Cache-Control"], "public, max-age=60, stale-while-revalidate=300")
        self.assertNotEqual(first["ETag"], other_query["ETag"])

        unchanged = self.client.get(
            "/projects/archive/",
            {"page_size": 2},
            HTTP_IF_NONE_MATCH=f'"other", W/{first["ETag"]}',
        )
        self.assertEqual(unchanged.status_code, 304)
        self.assertEqual(unchanged.content, b"")
        self.assertEqual(unchanged["ETag"], first["ETag"])

        self.alpha.project_title = "Updated title"
        self.alpha.save(update_fields=["project_title", "updated_at"])
        changed = self.client.get("/projects/archive/", {"page_size": 2}, HTTP_IF_NONE_MATCH=first["ETag"])
        self.assertEqual(changed.status_code, 200)
        self.assertNotEqual(changed["ETag"], first["ETag"])

    def test_legacy_past_all_contract_remains_a_full_flat_detail_list(self):
        response = self.client.get("/projects/past-all/", {"page": 1, "page_size": 1, "search": "nothing"})
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 4)
        self.assertIn("abstract", response.data[0])
        self.assertIn("student_names", response.data[0])
