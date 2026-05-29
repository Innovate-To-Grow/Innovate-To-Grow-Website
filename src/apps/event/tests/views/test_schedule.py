from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import CurrentProjectSchedule
from apps.event.services import sync_schedule
from apps.event.tests.helpers import sample_projects_records, sample_tracks_records


class CurrentEventScheduleViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_no_config_returns_404(self):
        response = self.client.get("/event/schedule/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "No schedule configured.")

    def test_config_without_schedule_returns_404(self):
        CurrentProjectSchedule.objects.create(name="Demo Day")
        response = self.client.get("/event/schedule/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "No schedule available.")

    def test_returns_payload_for_schedule(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        sync_schedule(config, tracks_records=sample_tracks_records(), projects_records=sample_projects_records())

        response = self.client.get("/event/schedule/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["event"]["name"], "Demo Day")
        self.assertEqual(response.data["expo"]["title"], "EXPO: POSTERS AND DEMOS")
        self.assertEqual(response.data["awards"]["title"], "AWARDS & RECEPTION")
        self.assertEqual(len(response.data["sections"]), 3)
        self.assertEqual(response.data["sections"][0]["code"], "CAP")
        self.assertEqual(response.data["sections"][0]["tracks"][0]["track_number"], 1)
        self.assertEqual(response.data["sections"][0]["tracks"][0]["slots"][0]["team_number"], "CAP-101")
        self.assertEqual(response.data["projects"][0]["team_number"], "CAP-101")

    def test_schedule_id_query_selects_non_active_schedule(self):
        active = CurrentProjectSchedule.objects.create(name="Active Demo Day")
        sync_schedule(active, tracks_records=sample_tracks_records(), projects_records=sample_projects_records())
        archived = CurrentProjectSchedule.objects.create(name="Archived Demo Day", is_active=False)
        sync_schedule(archived, tracks_records=sample_tracks_records(), projects_records=sample_projects_records())

        default_response = self.client.get("/event/schedule/")
        selected_response = self.client.get("/event/schedule/", {"schedule_id": str(archived.pk)})

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(default_response.data["event"]["name"], "Active Demo Day")
        self.assertEqual(selected_response.status_code, 200)
        self.assertEqual(selected_response.data["event"]["name"], "Archived Demo Day")

    def test_projects_include_non_presenting_teams(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        tracks = [{"Track": 1, "Room": "Granite", "Class": "CAP", "Topic": "FoodTech"}]
        projects = [
            {"Track": 1, "Order": 1, "Class": "CAP", "Team#": "CAP-101", "Project Title": "Smart Farm"},
            {"Track": "(fall)", "Order": 1, "Class": "CAP", "Team#": "CAP-FALL", "Project Title": "Archived"},
        ]
        sync_schedule(config, tracks_records=tracks, projects_records=projects)

        response = self.client.get("/event/schedule/")

        self.assertEqual(response.status_code, 200)
        team_numbers = {row["team_number"] for row in response.data["projects"]}
        self.assertIn("CAP-101", team_numbers)
        self.assertIn("CAP-FALL", team_numbers)

        fall_row = next(row for row in response.data["projects"] if row["team_number"] == "CAP-FALL")
        self.assertFalse(fall_row["is_presenting"])
