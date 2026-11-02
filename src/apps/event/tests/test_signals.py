from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import CurrentProject, CurrentProjectSchedule


class CurrentProjectsCacheInvalidationTest(TestCase):
    """/event/projects/ is cached; every edit to what it serves clears the entry once committed."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.config = CurrentProjectSchedule.objects.create(name="2026 Spring", is_active=True)
        self.project = CurrentProject.objects.create(
            schedule=self.config, team_number="101", project_title="Original", is_presenting=True
        )
        self.assertEqual(self.client.get("/event/projects/").status_code, 200)

    def _served(self):
        response = self.client.get("/event/projects/")
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_admin_edit_of_a_current_project_is_served_at_once(self):
        with self.captureOnCommitCallbacks(execute=True):
            project = CurrentProject.objects.get(pk=self.project.pk)
            project.project_title = "Renamed"
            project.is_presenting = False
            project.save()

        served = self._served()["projects"][0]
        self.assertEqual(served["project_title"], "Renamed")
        self.assertFalse(served["is_presenting"])

    def test_deleting_a_current_project_is_served_at_once(self):
        with self.captureOnCommitCallbacks(execute=True):
            CurrentProject.objects.get(pk=self.project.pk).delete()

        self.assertEqual(self._served()["projects"], [])

    def test_activating_another_schedule_is_served_at_once(self):
        with self.captureOnCommitCallbacks(execute=True):
            CurrentProjectSchedule.objects.create(name="2026 Fall", is_active=True)

        self.assertEqual(self._served()["schedule"]["name"], "2026 Fall")

    def test_editing_an_archived_schedule_project_keeps_the_cache(self):
        archived = CurrentProjectSchedule.objects.create(name="2025 Fall", is_active=False)
        cache.set("event:current-projects", {"cached": True}, timeout=300)

        with self.captureOnCommitCallbacks(execute=True):
            CurrentProject.objects.create(schedule=archived, team_number="9", project_title="Old")

        self.assertEqual(cache.get("event:current-projects"), {"cached": True})
