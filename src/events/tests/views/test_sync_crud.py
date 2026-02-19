"""
View tests for events app — EventSyncAPIView auth and CRUD operations.
"""

from datetime import date, time

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import Event


class EventSyncAuthAndCRUDTest(TestCase):
    """Test EventSyncAPIView auth and CRUD (POST /api/events/sync/)."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.url = reverse("events:event-sync")
        self.api_key = "test-api-key-123"

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_requires_api_key_authentication(self):
        """Test requires API key authentication (401 without key)."""
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
            },
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_rejects_invalid_api_key(self):
        """Test rejects invalid API key (401 with wrong key)."""
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
            },
        }
        self.client.credentials(HTTP_X_API_KEY="wrong-key")
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_creates_new_event_when_none_exists(self):
        """Test creates new event when none exists (with basic_info)."""
        payload = {
            "basic_info": {
                "event_name": "New Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
                "upper_bullet_points": ["Point 1"],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")

        # Verify event was created
        event = Event.objects.get(event_name="New Event")
        self.assertEqual(event.event_name, "New Event")
        self.assertEqual(event.upper_bullet_points, ["Point 1"])

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_updates_existing_event(self):
        """Test updates existing event."""
        event = Event.objects.create(
            event_name="Old Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

        payload = {
            "basic_info": {
                "event_name": "Updated Event",
                "event_date": "2024-06-16",
                "event_time": "10:00:00",
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify event was updated
        event.refresh_from_db()
        self.assertEqual(event.event_name, "Updated Event")
        self.assertEqual(event.event_date, date(2024, 6, 16))

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_processes_basic_info_only(self):
        """Test processes basic_info only."""
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
                "upper_bullet_points": ["Point 1"],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = Event.objects.get()
        self.assertEqual(event.event_name, "Test Event")
        self.assertEqual(event.upper_bullet_points, ["Point 1"])

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_processes_schedule_only(self):
        """Test processes schedule only (creates full hierarchy)."""
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
                            "start_time": "13:00:00",
                            "presentations": [
                                {
                                    "order": 1,
                                    "team_id": "CSE-314",
                                    "team_name": "Team Alpha",
                                    "project_title": "Amazing Project",
                                    "organization": "Org A",
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

        # Verify hierarchy was created
        program = event.programs.get(program_name="CSE Program")
        track = program.tracks.get(track_name="Track 1")
        presentation = track.presentations.get(order=1)
        self.assertEqual(presentation.team_id, "CSE-314")
