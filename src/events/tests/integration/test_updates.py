"""
Integration tests for events sync update flows.
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import Event


class FullSyncUpdateFlowTest(TestCase):
    """Test full sync update and real-world payload flows."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.sync_url = reverse("events:event-sync")
        self.retrieve_url = reverse("events:event-retrieve")
        self.api_key = "test-api-key-123"

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_multiple_syncs_updates_vs_creates(self):
        """Test multiple syncs (updates vs creates)."""
        # First sync
        payload1 = {
            "basic_info": {
                "event_name": "First Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
            },
            "schedule": [
                {
                    "program_name": "Program 1",
                    "tracks": [
                        {
                            "track_name": "Track 1",
                            "room": "Room A",
                            "presentations": [
                                {
                                    "order": 1,
                                    "team_name": "Team A",
                                    "project_title": "Project A",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response1 = self.client.post(self.sync_url, payload1, format="json")
        self.assertEqual(response1.status_code, status.HTTP_200_OK)

        event = Event.objects.get()
        event_uuid = event.event_uuid
        self.assertEqual(event.event_name, "First Event")
        self.assertEqual(event.programs.count(), 1)

        # Second sync - should update existing event
        payload2 = {
            "basic_info": {
                "event_name": "Updated Event",
                "event_date": "2024-06-16",
                "event_time": "10:00:00",
            },
            "schedule": [
                {
                    "program_name": "Program 2",
                    "tracks": [
                        {
                            "track_name": "Track 2",
                            "room": "Room B",
                            "presentations": [
                                {
                                    "order": 1,
                                    "team_name": "Team B",
                                    "project_title": "Project B",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        response2 = self.client.post(self.sync_url, payload2, format="json")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

        # Verify event was updated (same UUID, different data)
        event.refresh_from_db()
        self.assertEqual(event.event_uuid, event_uuid)  # Same event
        self.assertEqual(event.event_name, "Updated Event")  # Updated name
        self.assertEqual(event.programs.count(), 1)  # Old program deleted, new one created
        self.assertEqual(event.programs.first().program_name, "Program 2")
