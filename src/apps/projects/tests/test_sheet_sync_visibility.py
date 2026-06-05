"""Pins the documented interaction between sheet sync and the past-all API.

The /projects/past-all/ endpoint hides the newest *published* semester (treated
as the in-flight "current" semester, owned by the event flow). A sheet sync only
publishes the semesters it imports, so as long as the active event semester is
newer than everything in the sheet, syncing historical rows never hides it.
"""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import PastProjectsSheetConfig, Project, Semester
from apps.projects.services.sheet_sync import sync_past_projects


class SheetSyncVisibilityTest(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()
        self.config = PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)

    def test_current_semester_stays_hidden_after_sync(self):
        # Event-owned current semester (newest published), populated outside the sheet.
        current = Semester.objects.create(year=2026, season=1, is_published=True)
        Project.objects.create(semester=current, project_title="Current Project", source=Project.Source.MANUAL)

        # Sheet carries only older history.
        records = [
            {
                "Year-Semester": "2024-2 Fall",
                "Class": "CSE",
                "Team#": "101",
                "Team Name": "Alpha",
                "Project Title": "Historical Project",
                "Organization": "TechCorp",
                "Industry": "Software",
                "Abstract": "",
                "Student Names": "",
            }
        ]
        sync_past_projects(self.config, records=records)

        response = self.api.get("/projects/past-all/")
        titles = [p["project_title"] for p in response.data]
        # The current semester is still excluded; synced history is shown.
        self.assertNotIn("Current Project", titles)
        self.assertIn("Historical Project", titles)
