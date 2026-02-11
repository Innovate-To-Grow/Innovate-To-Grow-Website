"""
Integration tests for events app.
"""

from datetime import date, time

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ..models import Event


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
        """Test sync → retrieve flow (data persists correctly)."""
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
