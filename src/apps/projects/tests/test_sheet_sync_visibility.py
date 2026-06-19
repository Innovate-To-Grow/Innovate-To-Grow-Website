"""Pins the documented interaction between sheet sync and the past-all API.

The /projects/past-all/ endpoint lists every published semester, including the newest one. A sheet
sync publishes the semesters it imports, so synced history (including the most recent term) appears
in past projects immediately.
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

    def test_newest_semester_visible_after_sync(self):
        # Newest published semester, populated outside the sheet.
        newest = Semester.objects.create(year=2026, season=1, is_published=True)
        Project.objects.create(semester=newest, project_title="Newest Project", source=Project.Source.MANUAL)

        # Sheet carries older history.
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
        # The newest semester is no longer hidden; synced history is shown alongside it.
        self.assertIn("Newest Project", titles)
        self.assertIn("Historical Project", titles)
