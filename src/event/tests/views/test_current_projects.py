from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from event.models import CurrentProject, CurrentProjectSchedule


class CurrentProjectsAPIViewTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def test_returns_projects_for_active_schedule(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        CurrentProject.objects.create(schedule=config, project_title="Fall Project", team_number="T1")

        response = self.client.get("/event/projects/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["schedule"]["name"], "Demo Day")
        self.assertEqual(len(response.data["projects"]), 1)
        self.assertEqual(response.data["projects"][0]["project_title"], "Fall Project")

    def test_includes_project_fields(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        CurrentProject.objects.create(
            schedule=config,
            project_title="Test Project",
            team_name="Team Alpha",
            team_number="T1",
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
        self.assertIn("is_presenting", project)

    def test_returns_404_when_no_active_schedule(self):
        CurrentProjectSchedule.objects.create(name="Inactive", is_active=False)

        response = self.client.get("/event/projects/")

        self.assertEqual(response.status_code, 404)

    def test_no_auth_required(self):
        CurrentProjectSchedule.objects.create(name="Demo Day")

        response = self.client.get("/event/projects/")

        self.assertEqual(response.status_code, 200)

    def test_cache_works(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        CurrentProject.objects.create(schedule=config, project_title="Cached Project", team_number="T1")

        response1 = self.client.get("/event/projects/")
        self.assertEqual(response1.status_code, 200)

        cached = cache.get("event:current-projects")
        self.assertIsNotNone(cached)

        response2 = self.client.get("/event/projects/")
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.data["projects"][0]["project_title"], "Cached Project")

    def test_response_shape(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        CurrentProject.objects.create(schedule=config, project_title="Shape Test", team_number="T1")

        response = self.client.get("/event/projects/")

        self.assertIn("schedule", response.data)
        self.assertIn("id", response.data["schedule"])
        self.assertIn("name", response.data["schedule"])
        self.assertIn("projects", response.data)
        self.assertIsInstance(response.data["projects"], list)
