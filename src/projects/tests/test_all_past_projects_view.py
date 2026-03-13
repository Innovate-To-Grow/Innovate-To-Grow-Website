from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from projects.models import Project, Semester


class AllPastProjectsAPIViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Create semesters: current (most recent published) and two past
        self.current = Semester.objects.create(year=2025, season=2, is_published=True)
        self.past1 = Semester.objects.create(year=2025, season=1, is_published=True)
        self.past2 = Semester.objects.create(year=2024, season=2, is_published=True)
        self.unpublished = Semester.objects.create(year=2024, season=1, is_published=False)

        # Create projects
        self.current_project = Project.objects.create(
            semester=self.current, project_title="Current Project", team_number="T01",
            class_code="ENGR 120", team_name="Alpha", organization="Acme",
        )
        self.past_project1 = Project.objects.create(
            semester=self.past1, project_title="Past Project 1", team_number="T01",
            class_code="ENGR 120", team_name="Beta", organization="Beta Inc",
            abstract="An abstract", student_names="Alice",
        )
        self.past_project2 = Project.objects.create(
            semester=self.past2, project_title="Past Project 2", team_number="T02",
            class_code="ME 150", team_name="Gamma", industry="Tech",
        )
        self.unpub_project = Project.objects.create(
            semester=self.unpublished, project_title="Unpub Project", team_number="T01",
        )

    def test_returns_flat_list(self):
        response = self.client.get("/projects/past-all/")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)

    def test_excludes_current_semester(self):
        response = self.client.get("/projects/past-all/")
        titles = [p["project_title"] for p in response.data]
        self.assertNotIn("Current Project", titles)

    def test_excludes_unpublished(self):
        response = self.client.get("/projects/past-all/")
        titles = [p["project_title"] for p in response.data]
        self.assertNotIn("Unpub Project", titles)

    def test_includes_past_projects(self):
        response = self.client.get("/projects/past-all/")
        titles = [p["project_title"] for p in response.data]
        self.assertIn("Past Project 1", titles)
        self.assertIn("Past Project 2", titles)

    def test_response_includes_semester_label(self):
        response = self.client.get("/projects/past-all/")
        self.assertTrue(len(response.data) > 0)
        self.assertIn("semester_label", response.data[0])

    def test_response_includes_all_table_fields(self):
        response = self.client.get("/projects/past-all/")
        project = next(p for p in response.data if p["project_title"] == "Past Project 1")
        self.assertEqual(project["abstract"], "An abstract")
        self.assertEqual(project["student_names"], "Alice")
        self.assertEqual(project["team_name"], "Beta")

    def test_no_auth_required(self):
        # No authentication set on client
        response = self.client.get("/projects/past-all/")
        self.assertEqual(response.status_code, 200)

    def test_ordering(self):
        response = self.client.get("/projects/past-all/")
        # past1 (2025-1) should come before past2 (2024-2)
        titles = [p["project_title"] for p in response.data]
        self.assertEqual(titles.index("Past Project 1"), 0)
        self.assertEqual(titles.index("Past Project 2"), 1)

    def test_cache_works(self):
        # First request populates cache
        response1 = self.client.get("/projects/past-all/")
        self.assertEqual(response1.status_code, 200)

        # Verify cache is set
        cached = cache.get("projects:past-all")
        self.assertIsNotNone(cached)
        self.assertEqual(len(cached), 2)

        # Second request should use cache
        response2 = self.client.get("/projects/past-all/")
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(len(response2.data), 2)
