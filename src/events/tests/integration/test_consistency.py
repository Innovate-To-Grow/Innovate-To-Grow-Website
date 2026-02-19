"""
Integration tests for events data consistency after sync operations.
"""

from datetime import date, time

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import Event


class DataConsistencyTest(TestCase):
    """Test data consistency after sync operations."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.sync_url = reverse("events:event-sync")
        self.api_key = "test-api-key-123"

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_program_track_presentation_relationships_maintained(self):
        """Test program/track/presentation relationships maintained after sync."""
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
        response = self.client.post(self.sync_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify relationships
        event = Event.objects.get()
        program = event.programs.first()
        track = program.tracks.first()
        presentation = track.presentations.first()

        self.assertEqual(presentation.track, track)
        self.assertEqual(track.program, program)
        self.assertEqual(program.event, event)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_winners_linked_to_correct_event(self):
        """Test winners linked to correct event."""
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
                    {"program_name": "Program 1", "award_winner": "Award Winner"},
                ],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.sync_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify winners are linked to correct event
        winner = event.track_winners.first()
        award = event.special_award_winners.first()
        self.assertEqual(winner.event, event)
        self.assertEqual(award.event, event)

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_expo_reception_tables_preserve_structure(self):
        """Test expo/reception tables preserve structure."""
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
            },
            "expo_table": [
                {"time": "Room:", "description": "Room A"},
                {"time": "10:00 AM", "description": "Event 1"},
                {"time": "11:00 AM", "description": "Event 2"},
            ],
            "reception_table": [
                {"time": "Room:", "description": "Room B"},
                {"time": "5:00 PM", "description": "Awards"},
                {"time": "6:00 PM", "description": "Dinner"},
            ],
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.sync_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = Event.objects.get()
        # Verify structure preserved (header rows filtered out)
        self.assertEqual(len(event.expo_table), 2)
        self.assertEqual(len(event.reception_table), 2)
        # Verify room applied correctly
        self.assertEqual(event.expo_table[0]["room"], "Room A")
        self.assertEqual(event.reception_table[0]["room"], "Room B")

    @override_settings(EVENTS_API_KEY="test-api-key-123")
    def test_bullet_points_preserve_markdown_content(self):
        """Test bullet points preserve markdown content."""
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
                "upper_bullet_points": [
                    "**Bold text**",
                    "_Italic text_",
                    "__Underlined text__",
                ],
                "lower_bullet_points": [
                    "Regular text",
                ],
            },
        }
        self.client.credentials(HTTP_X_API_KEY=self.api_key)
        response = self.client.post(self.sync_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        event = Event.objects.get()
        self.assertEqual(event.upper_bullet_points[0], "**Bold text**")
        self.assertEqual(event.upper_bullet_points[1], "_Italic text_")
        self.assertEqual(event.upper_bullet_points[2], "__Underlined text__")
        self.assertEqual(event.lower_bullet_points[0], "Regular text")
