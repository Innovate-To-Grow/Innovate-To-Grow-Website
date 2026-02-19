"""
Integration tests for events sync and retrieve flows.
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import Event


class FullSyncFlowTest(TestCase):
    """Test full sync and retrieve flows."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.sync_url = reverse("events:event-sync")
        self.retrieve_url = reverse("events:event-retrieve")
        self.api_key = "test-api-key-123"

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_complete_sync_all_sections(self):
        """Test complete sync: basic_info + schedule + expo_table + reception_table + winners."""
        payload = {
            "basic_info": {
                "event_name": "Complete Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
                "upper_bullet_points": ["**Bold** point", "_Italic_ point"],
                "lower_bullet_points": ["Lower point"],
            },
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
                                },
                                {
                                    "order": 2,
                                    "project_title": "Break",
                                },
                            ],
                        }
                    ],
                }
            ],
            "expo_table": [
                {"time": "Room:", "description": "Room A"},
                {"time": "10:00 AM", "description": "Expo start"},
            ],
            "reception_table": [
                {"time": "Room:", "description": "Room B"},
                {"time": "5:00 PM", "description": "Reception"},
            ],
            "winners": {
                "track_winners": [
                    {"track_name": "Track 1", "winner_name": "Team Alpha"},
                ],
                "special_awards": [
                    {"program_name": "CSE Program", "award_winner": "Team Beta"},
                ],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.sync_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")

        # Verify all data was saved
        event = Event.objects.get()
        self.assertEqual(event.event_name, "Complete Event")
        self.assertEqual(len(event.upper_bullet_points), 2)
        self.assertEqual(event.programs.count(), 1)
        self.assertEqual(event.programs.first().tracks.count(), 1)
        self.assertEqual(event.programs.first().tracks.first().presentations.count(), 2)
        self.assertEqual(len(event.expo_table), 1)
        self.assertEqual(len(event.reception_table), 1)
        self.assertEqual(event.track_winners.count(), 1)
        self.assertEqual(event.special_award_winners.count(), 1)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_sync_then_retrieve_flow(self):
        """Test sync -> retrieve flow (data persists correctly)."""
        # Sync data
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
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        sync_response = self.client.post(self.sync_url, payload, format="json")
        self.assertEqual(sync_response.status_code, status.HTTP_200_OK)

        # Retrieve data
        retrieve_response = self.client.get(self.retrieve_url)
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)

        # Verify retrieved data matches synced data
        self.assertEqual(retrieve_response.data["event_name"], "Test Event")
        self.assertEqual(len(retrieve_response.data["programs"]), 1)
        self.assertEqual(retrieve_response.data["programs"][0]["program_name"], "CSE Program")
        self.assertEqual(len(retrieve_response.data["programs"][0]["tracks"]), 1)
        self.assertEqual(len(retrieve_response.data["programs"][0]["tracks"][0]["presentations"]), 1)
