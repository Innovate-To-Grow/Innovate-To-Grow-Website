"""
View tests for events app — EventSyncAPIView section processing.
"""

from datetime import date, time

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import Event


class EventSyncSectionsTest(TestCase):
    """Test EventSyncAPIView section processing (POST /api/events/sync/)."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.url = reverse("events:event-sync")
        self.api_key = "test-api-key-123"

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_processes_expo_table_only(self):
        """Test processes expo_table only."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

        payload = {
            "expo_table": [
                {"time": "Room:", "description": "Room A"},
                {"time": "10:00 AM", "description": "Expo start"},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event.refresh_from_db()
        self.assertEqual(len(event.expo_table), 1)
        self.assertEqual(event.expo_table[0]["time"], "10:00 AM")
        self.assertEqual(event.expo_table[0]["room"], "Room A")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_processes_reception_table_only(self):
        """Test processes reception_table only."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

        payload = {
            "reception_table": [
                {"time": "Room:", "description": "Room B"},
                {"time": "5:00 PM", "description": "Reception"},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event.refresh_from_db()
        self.assertEqual(len(event.reception_table), 1)
        self.assertEqual(event.reception_table[0]["time"], "5:00 PM")
        self.assertEqual(event.reception_table[0]["room"], "Room B")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_processes_winners_only(self):
        """Test processes winners only."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

        payload = {
            "winners": {
                "track_winners": [
                    {"track_name": "Track 1", "winner_name": "Winner 1"},
                ],
                "special_awards": [
                    {"program_name": "CSE Program", "award_winner": "Award Winner"},
                ],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(event.track_winners.count(), 1)
        self.assertEqual(event.special_award_winners.count(), 1)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_processes_multiple_sections_together(self):
        """Test processes multiple sections together."""
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
            },
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
                                    "team_name": "Team Alpha",
                                    "project_title": "Project",
                                }
                            ],
                        }
                    ],
                }
            ],
            "expo_table": [
                {"time": "Room:", "description": "Room A"},
                {"time": "10:00 AM", "description": "Expo"},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = Event.objects.get()
        self.assertEqual(event.event_name, "Test Event")
        self.assertEqual(event.programs.count(), 1)
        self.assertEqual(len(event.expo_table), 1)
