"""
View tests for events app — EventSyncAPIView formatting and edge cases.
"""

from datetime import date, time

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import Event


class EventSyncFormattingTest(TestCase):
    """Test EventSyncAPIView formatting/edge cases (POST /api/events/sync/)."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.url = reverse("events:event-sync")
        self.api_key = "test-api-key-123"

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_time_formatting_gmt_timestamp(self):
        """Test time formatting in expo_table (GMT timestamp -> 12-hour AM/PM)."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

        payload = {
            "expo_table": [
                {"time": "Room:", "description": "Room A"},
                {"time": "2024-06-15T14:30:00Z", "description": "Expo start"},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event.refresh_from_db()
        # 14:30 UTC should be formatted as 2:30 PM (or adjusted for timezone)
        self.assertIn("PM", event.expo_table[0]["time"])

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_time_formatting_without_am_pm(self):
        """Test time formatting adds AM/PM when missing."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

        payload = {
            "expo_table": [
                {"time": "Room:", "description": "Room A"},
                {"time": "14:30", "description": "Expo start"},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event.refresh_from_db()
        # Should add AM/PM
        self.assertIn("PM", event.expo_table[0]["time"])

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_room_extraction_from_header_rows(self):
        """Test room extraction from header rows (time="Room:")."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

        payload = {
            "expo_table": [
                {"time": "Room:", "description": "Room A"},
                {"time": "10:00 AM", "description": "Expo start"},
                {"time": "11:00 AM", "description": "Expo continue"},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event.refresh_from_db()
        # Both rows should have room from header
        self.assertEqual(event.expo_table[0]["room"], "Room A")
        self.assertEqual(event.expo_table[1]["room"], "Room A")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_room_application_to_subsequent_rows(self):
        """Test room application to subsequent rows."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

        payload = {
            "expo_table": [
                {"time": "Room:", "description": "Room A"},
                {"time": "10:00 AM", "description": "First"},
                {"time": "11:00 AM", "description": "Second"},
                {"time": "Room:", "description": "Room B"},
                {"time": "12:00 PM", "description": "Third"},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event.refresh_from_db()
        # First two rows should have Room A, third should have Room B
        self.assertEqual(event.expo_table[0]["room"], "Room A")
        self.assertEqual(event.expo_table[1]["room"], "Room A")
        self.assertEqual(event.expo_table[2]["room"], "Room B")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_handles_missing_room_headers(self):
        """Test handles missing room headers."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

        payload = {
            "expo_table": [
                {"time": "10:00 AM", "room": "Room A", "description": "Expo start"},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event.refresh_from_db()
        # Should use room from row field
        self.assertEqual(event.expo_table[0]["room"], "Room A")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_break_handling_null_team_fields_allowed(self):
        """Test break handling (null team_id/team_name allowed)."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

        payload = {
            "schedule": [
                {
                    "program_name": "CSE Program",
                    "tracks": [
                        {
                            "track_name": "Track 1",
                            "room": "Room A",
                            "presentations": [
                                {
                                    "order": 1,
                                    "project_title": "Break",
                                    # No team_name or team_id
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        presentation = event.programs.first().tracks.first().presentations.first()
        self.assertIsNone(presentation.team_id)
        self.assertIsNone(presentation.team_name)
        self.assertEqual(presentation.project_title, "Break")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_response_includes_event_uuid(self):
        """Test response includes event_uuid."""
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("event_uuid", response.data)

        event = Event.objects.get()
        self.assertEqual(response.data["event_uuid"], str(event.event_uuid))
