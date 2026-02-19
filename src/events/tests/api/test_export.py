"""
Tests for Event sheet export API — authentication, 404, and full-mode export.
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ..factories import create_live_event


class EventSheetExportAPIViewTest(TestCase):
    """Test GET /api/events/sync/export/ — auth, 404, and full mode."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("events:event-sync-export")
        self.api_key = "test-api-key-123"

    def _auth(self):
        self.client.credentials(HTTP_X_API_KEY=self.api_key)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_requires_api_key_authentication(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN})

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_rejects_invalid_api_key(self):
        self.client.credentials(HTTP_X_API_KEY="invalid-key")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_returns_404_when_no_live_event(self):
        self._auth()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_full_mode_returns_sheet_friendly_payload(self):
        event = create_live_event()
        self._auth()

        response = self.client.get(self.url, {"mode": "full"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["meta"]["source"], "i2g-db")
        self.assertEqual(response.data["meta"]["scope"], "live_event")
        self.assertEqual(response.data["meta"]["mode"], "full")
        self.assertTrue(response.data["meta"]["delta_changed"])
        self.assertEqual(response.data["meta"]["event"]["event_uuid"], str(event.event_uuid))
        self.assertEqual(response.data["meta"]["event"]["slug"], event.slug)
        self.assertEqual(response.data["meta"]["event"]["event_name"], event.event_name)

        worksheets = response.data["worksheets"]
        self.assertEqual(
            set(worksheets.keys()),
            {
                "event_basic",
                "event_bullets",
                "event_expo",
                "event_reception",
                "event_schedule",
                "event_track_winners",
                "event_special_awards",
            },
        )

        event_basic = worksheets["event_basic"][0]
        self.assertEqual(event_basic["event_uuid"], str(event.event_uuid))
        self.assertEqual(event_basic["event_slug"], event.slug)
        self.assertEqual(event_basic["event_name"], event.event_name)
        self.assertEqual(event_basic["is_published"], True)
        self.assertEqual(event_basic["is_live"], True)
        self.assertTrue(event_basic["updated_at"].endswith("Z"))

        event_bullets = worksheets["event_bullets"]
        self.assertEqual(event_bullets[0]["section"], "upper")
        self.assertEqual(event_bullets[0]["position"], 1)
        self.assertEqual(event_bullets[-1]["section"], "lower")

        schedule = worksheets["event_schedule"]
        self.assertGreaterEqual(len(schedule), 4)
        self.assertEqual(schedule[0]["program_name"], "Program A")
        self.assertEqual(schedule[0]["program_order"], 1)
        self.assertEqual(schedule[0]["track_name"], "Track A1")
        self.assertEqual(schedule[0]["track_order"], 1)
        self.assertEqual(schedule[0]["presentation_order"], 1)
        self.assertEqual(schedule[0]["team_id"], "A-101")
        self.assertFalse(schedule[0]["is_break"])

        break_row = [row for row in schedule if row["project_title"] == "Break"][0]
        self.assertTrue(break_row["is_break"])
        self.assertEqual(break_row["team_id"], "")
        self.assertEqual(break_row["team_name"], "")

        track_winners = worksheets["event_track_winners"]
        self.assertEqual(len(track_winners), 1)
        self.assertEqual(track_winners[0]["position"], 1)
        self.assertEqual(track_winners[0]["track_name"], "Track A1")

        special_awards = worksheets["event_special_awards"]
        self.assertEqual(len(special_awards), 1)
        self.assertEqual(special_awards[0]["position"], 1)
        self.assertEqual(special_awards[0]["program_name"], "Program A")
