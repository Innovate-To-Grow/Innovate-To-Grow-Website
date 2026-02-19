"""
Integration tests for events edge cases and error scenarios.
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import Event


class EdgeCasesTest(TestCase):
    """Test edge cases and error scenarios."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.sync_url = reverse("events:event-sync")
        self.api_key = "test-api-key-123"

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_sync_with_empty_arrays(self):
        """Test sync with empty arrays."""
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
            },
            "schedule": [],
            "expo_table": [],
            "reception_table": [],
            "winners": {
                "track_winners": [],
                "special_awards": [],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.sync_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = Event.objects.get()
        self.assertEqual(event.programs.count(), 0)
        self.assertEqual(len(event.expo_table), 0)
        self.assertEqual(len(event.reception_table), 0)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_sync_with_special_characters_in_text_fields(self):
        """Test sync with special characters in text fields."""
        payload = {
            "basic_info": {
                "event_name": "Test Event & More <Special>",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
            },
            "schedule": [
                {
                    "program_name": 'Program "A" & Program B',
                    "tracks": [
                        {
                            "track_name": "Track 1",
                            "room": "Room A",
                            "presentations": [
                                {
                                    "order": 1,
                                    "team_name": 'Team "Alpha" & Beta',
                                    "project_title": "Project <Title> & More",
                                    "organization": "Org & Co.",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.sync_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = Event.objects.get()
        self.assertEqual(event.event_name, "Test Event & More <Special>")
        presentation = event.programs.first().tracks.first().presentations.first()
        self.assertEqual(presentation.team_name, 'Team "Alpha" & Beta')
        self.assertEqual(presentation.project_title, "Project <Title> & More")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_sync_with_missing_optional_fields(self):
        """Test sync with missing optional fields."""
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
                # No upper_bullet_points or lower_bullet_points
            },
            "schedule": [
                {
                    "program_name": "CSE Program",
                    "tracks": [
                        {
                            "track_name": "Track 1",
                            "room": "Room A",
                            # No start_time
                            "presentations": [
                                {
                                    "order": 1,
                                    "project_title": "Break",
                                    # No team_id, team_name, or organization
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.sync_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = Event.objects.get()
        self.assertEqual(event.upper_bullet_points, [])
        track = event.programs.first().tracks.first()
        self.assertIsNone(track.start_time)
        presentation = track.presentations.first()
        self.assertIsNone(presentation.team_id)
        self.assertIsNone(presentation.team_name)
