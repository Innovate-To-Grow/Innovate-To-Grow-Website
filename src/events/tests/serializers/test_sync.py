"""
Serializer tests for EventSyncSerializer.
"""

from django.test import TestCase

from ...serializers import EventSyncSerializer


class EventSyncSerializerTest(TestCase):
    """Test EventSyncSerializer."""

    def test_validation_with_all_sections(self):
        """Test validation with all sections provided."""
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
                "upper_bullet_points": ["Point 1"],
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
            "expo_table": [{"time": "10:00 AM", "description": "Expo"}],
            "reception_table": [{"time": "5:00 PM", "description": "Reception"}],
            "winners": {
                "track_winners": [{"track_name": "Track 1", "winner_name": "Winner"}],
            },
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertTrue(serializer.is_valid())

    def test_validation_with_partial_sections(self):
        """Test validation with partial sections."""
        # Only basic_info
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
            },
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertTrue(serializer.is_valid())

        # Only schedule
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
                                    "team_name": "Team Alpha",
                                    "project_title": "Project",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertTrue(serializer.is_valid())

    def test_validation_requires_at_least_one_section(self):
        """Test validation requires at least one section."""
        payload = {}
        serializer = EventSyncSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_basic_info_validation(self):
        """Test basic_info validation (required fields)."""
        # Missing event_name
        payload = {
            "basic_info": {
                "event_date": "2024-06-15",
                "event_time": "09:00:00",
            },
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

        # Missing event_date
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_time": "09:00:00",
            },
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

        # Missing event_time
        payload = {
            "basic_info": {
                "event_name": "Test Event",
                "event_date": "2024-06-15",
            },
        }
        serializer = EventSyncSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
