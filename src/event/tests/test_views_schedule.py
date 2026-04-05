from django.test import TestCase
from rest_framework.test import APIClient

from event.models import CurrentProjectSchedule
from event.services import sync_schedule

from .test_services_schedule_sync import _projects_records, _tracks_records


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
        sync_schedule(config, tracks_records=_tracks_records(), projects_records=_projects_records())

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
