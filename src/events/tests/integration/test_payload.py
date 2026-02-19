"""
Integration tests for real-world Google Sheets payload sync.
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import Event


class RealWorldPayloadSyncTest(TestCase):
    """Test sync with real-world Google Sheets payload structure."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.sync_url = reverse("events:event-sync")
        self.api_key = "test-api-key-123"

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_sync_with_real_world_google_sheets_payload_structure(self):
        """Test sync with real-world Google Sheets payload structure."""
        # Simulate a realistic payload structure
        payload = {
            "basic_info": {
                "event_name": "Innovate to Grow 2024",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
                "upper_bullet_points": [
                    "Register **ASAP** to attend in person",
                    "Review schedule and teams below",
                ],
                "lower_bullet_points": [
                    "Event location: Main Hall",
                    "Parking available in Lot A",
                ],
            },
            "schedule": [
                {
                    "program_name": "CSE Software Engineering",
                    "tracks": [
                        {
                            "track_name": "Web Development",
                            "room": "Room 101",
                            "start_time": "13:00:00",
                            "presentations": [
                                {
                                    "order": 1,
                                    "team_id": "CSE-314",
                                    "team_name": "Team Alpha",
                                    "project_title": "E-Commerce Platform",
                                    "organization": "Tech Corp",
                                },
                                {
                                    "order": 2,
                                    "project_title": "Break",
                                },
                                {
                                    "order": 3,
                                    "team_id": "CSE-315",
                                    "team_name": "Team Beta",
                                    "project_title": "Social Media App",
                                    "organization": "Startup Inc",
                                },
                            ],
                        },
                        {
                            "track_name": "Mobile Development",
                            "room": "Room 102",
                            "start_time": "13:00:00",
                            "presentations": [
                                {
                                    "order": 1,
                                    "team_id": "CSE-316",
                                    "team_name": "Team Gamma",
                                    "project_title": "Fitness Tracker",
                                    "organization": "Health Co",
                                }
                            ],
                        },
                    ],
                },
                {
                    "program_name": "Civil Engineering",
                    "tracks": [
                        {
                            "track_name": "Infrastructure",
                            "room": "Room 201",
                            "start_time": "14:00:00",
                            "presentations": [
                                {
                                    "order": 1,
                                    "team_id": "CEE-101",
                                    "team_name": "Team Delta",
                                    "project_title": "Bridge Design",
                                    "organization": "Engineering Firm",
                                }
                            ],
                        }
                    ],
                },
            ],
            "expo_table": [
                {"time": "Room:", "description": "Expo Hall"},
                {"time": "10:00 AM", "description": "Poster session begins"},
                {"time": "11:30 AM", "description": "Demo showcase"},
            ],
            "reception_table": [
                {"time": "Room:", "description": "Grand Ballroom"},
                {"time": "5:00 PM", "description": "Awards ceremony"},
                {"time": "6:00 PM", "description": "Reception dinner"},
            ],
            "winners": {
                "track_winners": [
                    {"track_name": "Web Development", "winner_name": "Team Alpha"},
                    {"track_name": "Mobile Development", "winner_name": "Team Gamma"},
                    {"track_name": "Infrastructure", "winner_name": "Team Delta"},
                ],
                "special_awards": [
                    {"program_name": "CSE Software Engineering", "award_winner": "Team Beta - Innovation Award"},
                ],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.sync_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify complex structure
        event = Event.objects.get()
        self.assertEqual(event.event_name, "Innovate to Grow 2024")
        self.assertEqual(event.programs.count(), 2)

        cse_program = event.programs.get(program_name="CSE Software Engineering")
        self.assertEqual(cse_program.tracks.count(), 2)

        web_track = cse_program.tracks.get(track_name="Web Development")
        self.assertEqual(web_track.presentations.count(), 3)  # Including break

        self.assertEqual(event.track_winners.count(), 3)
        self.assertEqual(event.special_award_winners.count(), 1)
