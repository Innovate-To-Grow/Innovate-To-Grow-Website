from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from projects.models import Project, Semester


class CurrentProjectsAPIViewTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def test_returns_newest_published_semester(self):
        Semester.objects.create(year=2025, season=1, is_published=True)
        fall = Semester.objects.create(year=2025, season=2, is_published=True)
        Project.objects.create(semester=fall, project_title="Fall Project")

        response = self.client.get("/event/projects/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["label"], fall.label)
        self.assertEqual(len(response.data["projects"]), 1)
        self.assertEqual(response.data["projects"][0]["project_title"], "Fall Project")

    def test_includes_project_fields(self):
        semester = Semester.objects.create(year=2025, season=1, is_published=True)
        Project.objects.create(
            semester=semester,
            project_title="Test Project",
            team_name="Team Alpha",
            organization="Acme Corp",
            industry="Tech",
            class_code="CSE123",
        )

        response = self.client.get("/event/projects/")

        project = response.data["projects"][0]
        self.assertEqual(project["project_title"], "Test Project")
        self.assertEqual(project["team_name"], "Team Alpha")
        self.assertEqual(project["organization"], "Acme Corp")
        self.assertEqual(project["industry"], "Tech")
        self.assertEqual(project["class_code"], "CSE123")
        self.assertIn("id", project)

    def test_returns_404_when_no_published_semesters(self):
        Semester.objects.create(year=2025, season=1, is_published=False)

        response = self.client.get("/event/projects/")

        self.assertEqual(response.status_code, 404)

    def test_no_auth_required(self):
        Semester.objects.create(year=2025, season=1, is_published=True)

        response = self.client.get("/event/projects/")

        self.assertEqual(response.status_code, 200)

    def test_cache_works(self):
        semester = Semester.objects.create(year=2025, season=1, is_published=True)
        Project.objects.create(semester=semester, project_title="Cached Project")

        response1 = self.client.get("/event/projects/")
        self.assertEqual(response1.status_code, 200)

        cached = cache.get("event:current-projects")
        self.assertIsNotNone(cached)

        response2 = self.client.get("/event/projects/")
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.data["projects"][0]["project_title"], "Cached Project")

    def test_response_shape(self):
        semester = Semester.objects.create(year=2025, season=1, is_published=True)
        Project.objects.create(semester=semester, project_title="Shape Test")

        response = self.client.get("/event/projects/")

        self.assertIn("id", response.data)
        self.assertIn("year", response.data)
        self.assertIn("season", response.data)
        self.assertIn("label", response.data)
        self.assertIn("projects", response.data)
        self.assertIsInstance(response.data["projects"], list)
