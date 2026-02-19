"""
Serializer tests for EventReadSerializer.
"""

from datetime import date, time

from django.test import TestCase

from ...models import Event, Presentation, Program, SpecialAward, Track, TrackWinner
from ...serializers import EventReadSerializer


class EventReadSerializerTest(TestCase):
    """Test EventReadSerializer."""

    def setUp(self):
        """Set up test data."""
        self.event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            upper_bullet_points=["Point 1", "Point 2"],
            lower_bullet_points=["Lower 1"],
            expo_table=[{"time": "10:00 AM", "room": "A", "description": "Expo"}],
            reception_table=[{"time": "5:00 PM", "room": "B", "description": "Reception"}],
            is_published=True,
        )

    def test_serialize_complete_event_with_nested_data(self):
        """Test serialization of complete event with nested data."""
        program = Program.objects.create(
            event=self.event,
            program_name="CSE Program",
        )
        track = Track.objects.create(
            program=program,
            track_name="Track 1",
            room="Room A",
            start_time=time(13, 0),
        )
        presentation = Presentation.objects.create(
            track=track,
            order=1,
            team_id="CSE-314",
            team_name="Team Alpha",
            project_title="Amazing Project",
            organization="Org A",
        )
        winner = TrackWinner.objects.create(
            event=self.event,
            track_name="Track 1",
            winner_name="Team Alpha",
        )
        award = SpecialAward.objects.create(
            event=self.event,
            program_name="CSE Program",
            award_winner="Team Beta",
        )

        serializer = EventReadSerializer(self.event)
        data = serializer.data

        # Basic fields
        self.assertEqual(data["event_name"], "Test Event")
        self.assertEqual(data["event_date"], "2024-06-15")
        self.assertEqual(data["event_time"], "09:00:00")
        self.assertEqual(data["upper_bullet_points"], ["Point 1", "Point 2"])
        self.assertEqual(data["lower_bullet_points"], ["Lower 1"])
        self.assertEqual(data["expo_table"], [{"time": "10:00 AM", "room": "A", "description": "Expo"}])
        self.assertEqual(data["reception_table"], [{"time": "5:00 PM", "room": "B", "description": "Reception"}])
        self.assertTrue(data["is_published"])

        # Nested data
        self.assertEqual(len(data["programs"]), 1)
        self.assertEqual(data["programs"][0]["program_name"], "CSE Program")
        self.assertEqual(len(data["programs"][0]["tracks"]), 1)
        self.assertEqual(data["programs"][0]["tracks"][0]["track_name"], "Track 1")
        self.assertEqual(len(data["programs"][0]["tracks"][0]["presentations"]), 1)
        self.assertEqual(data["programs"][0]["tracks"][0]["presentations"][0]["team_id"], "CSE-314")

        # Winners
        self.assertEqual(len(data["track_winners"]), 1)
        self.assertEqual(data["track_winners"][0]["track_name"], "Track 1")
        self.assertEqual(len(data["special_awards"]), 1)
        self.assertEqual(data["special_awards"][0]["program_name"], "CSE Program")

    def test_serialize_with_empty_programs(self):
        """Test serialization with empty programs/tracks/presentations."""
        serializer = EventReadSerializer(self.event)
        data = serializer.data
        self.assertEqual(data["programs"], [])
        self.assertEqual(data["track_winners"], [])
        self.assertEqual(data["special_awards"], [])

    def test_json_field_serialization(self):
        """Test JSON field serialization."""
        serializer = EventReadSerializer(self.event)
        data = serializer.data
        self.assertIsInstance(data["upper_bullet_points"], list)
        self.assertIsInstance(data["lower_bullet_points"], list)
        self.assertIsInstance(data["expo_table"], list)
        self.assertIsInstance(data["reception_table"], list)

    def test_read_only_fields(self):
        """Test read-only fields (event_uuid, created_at, updated_at)."""
        serializer = EventReadSerializer(self.event)
        data = serializer.data
        self.assertIn("event_uuid", data)
        self.assertIn("created_at", data)
        self.assertIn("updated_at", data)
        # Verify read-only fields contain the correct values from the model
        original_uuid = str(self.event.event_uuid)
        self.assertEqual(data["event_uuid"], original_uuid)
        # Read-only fields should be present and match model values
        # (EventReadSerializer is read-only, so we can't test modification)
