"""
Serializer tests for schedule-related serializers
(PresentationSyncSerializer, TrackSyncSerializer, ProgramSyncSerializer).
"""

from django.test import TestCase

from ...serializers import (
    PresentationSyncSerializer,
    ProgramSyncSerializer,
    TrackSyncSerializer,
)


class PresentationSyncSerializerTest(TestCase):
    """Test PresentationSyncSerializer."""

    def test_validation_for_regular_presentation(self):
        """Test validation for regular presentation (team_name required)."""
        data = {
            "order": 1,
            "team_name": "Team Alpha",
            "project_title": "Amazing Project",
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_for_regular_presentation_missing_team_name(self):
        """Test validation fails for regular presentation without team_name."""
        data = {
            "order": 1,
            "project_title": "Amazing Project",
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("team_name", serializer.errors)

    def test_validation_for_break_entry_in_title(self):
        """Test validation for break entry (team_name optional when project_title contains 'break')."""
        data = {
            "order": 1,
            "project_title": "Break",
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_for_break_entry_in_organization(self):
        """Test validation for break entry (team_name optional when organization is 'break')."""
        data = {
            "order": 1,
            "project_title": "Lunch",
            "organization": "break",
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_order_validation(self):
        """Test order validation (must be >= 1)."""
        data = {
            "order": 0,
            "team_name": "Team Alpha",
            "project_title": "Project",
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("order", serializer.errors)

    def test_project_title_required(self):
        """Test project_title required."""
        data = {
            "order": 1,
            "team_name": "Team Alpha",
        }
        serializer = PresentationSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("project_title", serializer.errors)


class TrackSyncSerializerTest(TestCase):
    """Test TrackSyncSerializer."""

    def test_validation_track_name_room_required(self):
        """Test validation (track_name, room required)."""
        data = {
            "track_name": "Track 1",
            "room": "Room A",
            "presentations": [],
        }
        serializer = TrackSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_missing_track_name(self):
        """Test validation fails without track_name."""
        data = {
            "room": "Room A",
            "presentations": [],
        }
        serializer = TrackSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_start_time_optional(self):
        """Test start_time optional/nullable."""
        data = {
            "track_name": "Track 1",
            "room": "Room A",
            "start_time": None,
            "presentations": [],
        }
        serializer = TrackSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_presentations_array_validation(self):
        """Test presentations array validation."""
        data = {
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
        serializer = TrackSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())


class ProgramSyncSerializerTest(TestCase):
    """Test ProgramSyncSerializer."""

    def test_validation_program_name_required(self):
        """Test validation (program_name required)."""
        data = {
            "program_name": "CSE Program",
            "tracks": [],
        }
        serializer = ProgramSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_validation_missing_program_name(self):
        """Test validation fails without program_name."""
        data = {
            "tracks": [],
        }
        serializer = ProgramSyncSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_tracks_array_validation(self):
        """Test tracks array validation."""
        data = {
            "program_name": "CSE Program",
            "tracks": [
                {
                    "track_name": "Track 1",
                    "room": "Room A",
                    "presentations": [],
                }
            ],
        }
        serializer = ProgramSyncSerializer(data=data)
        self.assertTrue(serializer.is_valid())
