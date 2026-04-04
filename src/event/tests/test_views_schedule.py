from django.test import TestCase
from rest_framework.test import APIClient

from event.services import sync_event_schedule
from event.tests.helpers import make_event

from .test_services_schedule_sync import _projects_records, _tracks_records


class CurrentEventScheduleViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_no_live_event_returns_404(self):
        response = self.client.get("/event/schedule/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "No live event available.")

    def test_live_event_without_schedule_returns_404(self):
        make_event(is_live=True)
        response = self.client.get("/event/schedule/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "No live event schedule available.")

    def test_returns_payload_for_live_event_schedule(self):
        event = make_event(is_live=True)
        sync_event_schedule(event, tracks_records=_tracks_records(), projects_records=_projects_records())

        response = self.client.get("/event/schedule/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["event"]["name"], event.name)
        self.assertEqual(response.data["expo"]["title"], "EXPO: POSTERS AND DEMOS")
        self.assertEqual(response.data["awards"]["title"], "AWARDS & RECEPTION")
        self.assertEqual(len(response.data["sections"]), 3)
        self.assertEqual(response.data["sections"][0]["code"], "CAP")
        self.assertEqual(response.data["sections"][0]["tracks"][0]["track_number"], 1)
        self.assertEqual(response.data["sections"][0]["tracks"][0]["slots"][0]["team_number"], "CAP-101")
        self.assertEqual(response.data["projects"][0]["team_number"], "CAP-101")

    def test_returns_only_current_live_event_schedule(self):
        first = make_event(name="First", is_live=True)
        second = make_event(name="Second", is_live=True)
        sync_event_schedule(first, tracks_records=_tracks_records(), projects_records=_projects_records())
        sync_event_schedule(second, tracks_records=_tracks_records(), projects_records=_projects_records())

        response = self.client.get("/event/schedule/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["event"]["name"], "Second")
