"""
Tests for Event sheet export API — delta mode.
"""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ..factories import create_live_event, iso_utc


class EventSheetExportDeltaTest(TestCase):
    """Test GET /api/events/sync/export/?mode=delta endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("events:event-sync-export")
        self.api_key = "test-api-key-123"

    def _auth(self):
        self.client.credentials(HTTP_X_API_KEY=self.api_key)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_delta_mode_requires_since(self):
        create_live_event()
        self._auth()

        response = self.client.get(self.url, {"mode": "delta"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_delta_mode_rejects_invalid_since(self):
        create_live_event()
        self._auth()

        response = self.client.get(self.url, {"mode": "delta", "since": "not-a-date"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_delta_mode_returns_empty_worksheets_when_no_change(self):
        event = create_live_event()
        self._auth()

        since = iso_utc(event.updated_at + timedelta(minutes=5))
        response = self.client.get(self.url, {"mode": "delta", "since": since})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["meta"]["mode"], "delta")
        self.assertFalse(response.data["meta"]["delta_changed"])

        worksheets = response.data["worksheets"]
        for key in worksheets:
            self.assertEqual(worksheets[key], [])

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_delta_mode_returns_full_snapshot_when_changed(self):
        event = create_live_event()
        self._auth()

        since = iso_utc(event.updated_at - timedelta(minutes=5))
        response = self.client.get(self.url, {"mode": "delta", "since": since})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["meta"]["mode"], "delta")
        self.assertTrue(response.data["meta"]["delta_changed"])
        self.assertEqual(len(response.data["worksheets"]["event_basic"]), 1)
        self.assertGreater(len(response.data["worksheets"]["event_schedule"]), 0)
