from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from projects.models import Project, Semester


class CurrentProjectsAPIViewTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def test_returns_most_recent_published_semester(self):
        spring = Semester.objects.create(year=2025, season=1, is_published=True)
        fall = Semester.objects.create(year=2025, season=2, is_published=True)
        Project.objects.create(semester=spring, project_title="Spring Project")
        Project.objects.create(semester=fall, project_title="Fall Project")

        response = self.client.get("/projects/current/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["label"], fall.label)
        self.assertEqual(len(response.data["projects"]), 1)
        self.assertEqual(response.data["projects"][0]["project_title"], "Fall Project")

    def test_includes_project_fields(self):
        sem = Semester.objects.create(year=2025, season=1, is_published=True)
        Project.objects.create(
            semester=sem,
            project_title="Test Project",
            team_name="Team Alpha",
            organization="Acme Corp",
            industry="Tech",
            class_code="CSE123",
        )

        response = self.client.get("/projects/current/")

        project = response.data["projects"][0]
        self.assertEqual(project["project_title"], "Test Project")
        self.assertEqual(project["team_name"], "Team Alpha")
        self.assertEqual(project["organization"], "Acme Corp")
        self.assertEqual(project["industry"], "Tech")
        self.assertEqual(project["class_code"], "CSE123")
        self.assertIn("id", project)

    def test_excludes_unpublished_semesters(self):
        Semester.objects.create(year=2025, season=2, is_published=False)
        published = Semester.objects.create(year=2025, season=1, is_published=True)
        Project.objects.create(semester=published, project_title="Visible")

        response = self.client.get("/projects/current/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["label"], published.label)

    def test_returns_404_when_no_published_semesters(self):
        Semester.objects.create(year=2025, season=1, is_published=False)

        response = self.client.get("/projects/current/")

        self.assertEqual(response.status_code, 404)

    def test_no_auth_required(self):
        Semester.objects.create(year=2025, season=1, is_published=True)

        response = self.client.get("/projects/current/")

        self.assertEqual(response.status_code, 200)

    def test_returns_explicit_current_semester(self):
        """When is_current is set, that semester is returned even if not the newest."""
        spring = Semester.objects.create(year=2025, season=1, is_published=True, is_current=True)
        Semester.objects.create(year=2025, season=2, is_published=True)
        Project.objects.create(semester=spring, project_title="Spring Project")

        response = self.client.get("/projects/current/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["label"], spring.label)

    def test_fallback_when_no_current_set(self):
        """When no semester has is_current=True, falls back to newest published."""
        Semester.objects.create(year=2025, season=1, is_published=True)
        fall = Semester.objects.create(year=2025, season=2, is_published=True)

        response = self.client.get("/projects/current/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["label"], fall.label)


class PastProjectsAPIViewTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def test_excludes_current_semester(self):
        Semester.objects.create(year=2025, season=2, is_published=True)
        Semester.objects.create(year=2025, season=1, is_published=True)
        Semester.objects.create(year=2024, season=2, is_published=True)

        response = self.client.get("/projects/past/")

        self.assertEqual(response.status_code, 200)
        labels = [s["label"] for s in response.data["results"]]
        # Fall 2025 is current, should not appear in past
        self.assertNotIn("2025-2 Fall", labels)
        self.assertIn("2025-1 Spring", labels)
        self.assertIn("2024-2 Fall", labels)

    def test_includes_nested_projects(self):
        sem = Semester.objects.create(year=2024, season=1, is_published=True)
        # Need a "current" semester so 2024 Spring becomes "past"
        Semester.objects.create(year=2025, season=1, is_published=True)
        Project.objects.create(semester=sem, project_title="Old Project")

        response = self.client.get("/projects/past/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(len(response.data["results"][0]["projects"]), 1)
        self.assertEqual(response.data["results"][0]["projects"][0]["project_title"], "Old Project")

    def test_returns_paginated_response(self):
        # Create current + 6 past semesters (page_size=5)
        Semester.objects.create(year=2026, season=1, is_published=True)
        for year in range(2020, 2026):
            Semester.objects.create(year=year, season=1, is_published=True)

        response = self.client.get("/projects/past/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 5)
        self.assertIsNotNone(response.data["next"])

    def test_empty_when_only_one_published_semester(self):
        Semester.objects.create(year=2025, season=1, is_published=True)

        response = self.client.get("/projects/past/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_no_auth_required(self):
        response = self.client.get("/projects/past/")

        self.assertEqual(response.status_code, 200)

    def test_excludes_explicit_current_not_newest(self):
        """When an older semester is marked is_current, it is excluded from past."""
        spring = Semester.objects.create(year=2025, season=1, is_published=True, is_current=True)
        fall = Semester.objects.create(year=2025, season=2, is_published=True)
        Semester.objects.create(year=2024, season=2, is_published=True)

        response = self.client.get("/projects/past/")

        labels = [s["label"] for s in response.data["results"]]
        self.assertNotIn(spring.label, labels)
        # Fall 2025 is NOT current, so it should appear in past
        self.assertIn(fall.label, labels)


class ProjectDetailAPIViewTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def test_returns_project_detail(self):
        sem = Semester.objects.create(year=2025, season=1, is_published=True)
        project = Project.objects.create(
            semester=sem,
            project_title="Detail Project",
            team_name="Team Beta",
            team_number="5",
            organization="Test Org",
            industry="Healthcare",
            abstract="This is the abstract.",
            student_names="Alice, Bob, Charlie",
            class_code="ENGR101",
            track=1,
            presentation_order=3,
        )

        response = self.client.get(f"/projects/{project.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["project_title"], "Detail Project")
        self.assertEqual(response.data["team_name"], "Team Beta")
        self.assertEqual(response.data["team_number"], "5")
        self.assertEqual(response.data["organization"], "Test Org")
        self.assertEqual(response.data["industry"], "Healthcare")
        self.assertEqual(response.data["abstract"], "This is the abstract.")
        self.assertEqual(response.data["student_names"], "Alice, Bob, Charlie")
        self.assertEqual(response.data["class_code"], "ENGR101")
        self.assertEqual(response.data["track"], 1)
        self.assertEqual(response.data["presentation_order"], 3)

    def test_includes_semester_label(self):
        sem = Semester.objects.create(year=2025, season=1, is_published=True)
        project = Project.objects.create(semester=sem, project_title="Test")

        response = self.client.get(f"/projects/{project.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["semester_label"], sem.label)

    def test_not_found_returns_404(self):
        import uuid

        response = self.client.get(f"/projects/{uuid.uuid4()}/")

        self.assertEqual(response.status_code, 404)

    def test_no_auth_required(self):
        sem = Semester.objects.create(year=2025, season=1, is_published=True)
        project = Project.objects.create(semester=sem, project_title="Public")

        response = self.client.get(f"/projects/{project.id}/")

        self.assertEqual(response.status_code, 200)

    def test_excludes_projects_from_unpublished_semesters(self):
        sem = Semester.objects.create(year=2025, season=1, is_published=False)
        project = Project.objects.create(semester=sem, project_title="Draft Project")

        response = self.client.get(f"/projects/{project.id}/")

        self.assertEqual(response.status_code, 404)
