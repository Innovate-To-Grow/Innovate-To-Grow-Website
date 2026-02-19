"""
View tests for events app — EventRetrieveAPIView.
"""

from datetime import date, time

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import Event, Presentation, Program, Track


class EventRetrieveAPIViewTest(TestCase):
    """Test EventRetrieveAPIView (GET /api/events/)."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.url = reverse("events:event-retrieve")

    def test_returns_published_event_when_one_exists(self):
        """Test returns published event when one exists."""
        published_event = Event.objects.create(
            event_name="Published Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            is_published=True,
        )
        unpublished_event = Event.objects.create(
            event_name="Unpublished Event",
            event_date=date(2024, 6, 16),
            event_time=time(10, 0),
            is_published=False,
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["event_name"], "Published Event")
        self.assertEqual(response.data["event_uuid"], str(published_event.event_uuid))

    def test_returns_most_recent_event_when_no_published_events_exist(self):
        """Test returns most recent event when no published events exist."""
        event1 = Event.objects.create(
            event_name="Event 1",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            is_published=False,
        )
        event2 = Event.objects.create(
            event_name="Event 2",
            event_date=date(2024, 6, 16),
            event_time=time(10, 0),
            is_published=False,
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return most recent (event2, created later)
        self.assertEqual(response.data["event_name"], "Event 2")

    def test_returns_404_when_no_events_exist(self):
        """Test returns 404 when no events exist."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    def test_response_structure_matches_event_read_serializer(self):
        """Test response structure matches EventReadSerializer."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            is_published=True,
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check all expected fields are present
        self.assertIn("event_uuid", response.data)
        self.assertIn("event_name", response.data)
        self.assertIn("event_date", response.data)
        self.assertIn("event_time", response.data)
        self.assertIn("upper_bullet_points", response.data)
        self.assertIn("lower_bullet_points", response.data)
        self.assertIn("expo_table", response.data)
        self.assertIn("reception_table", response.data)
        self.assertIn("is_published", response.data)
        self.assertIn("programs", response.data)
        self.assertIn("track_winners", response.data)
        self.assertIn("special_awards", response.data)
        self.assertIn("created_at", response.data)
        self.assertIn("updated_at", response.data)

    def test_nested_data_structure(self):
        """Test nested data structure (programs -> tracks -> presentations)."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            is_published=True,
        )
        program = Program.objects.create(
            event=event,
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

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["programs"]), 1)
        self.assertEqual(response.data["programs"][0]["program_name"], "CSE Program")
        self.assertEqual(len(response.data["programs"][0]["tracks"]), 1)
        self.assertEqual(response.data["programs"][0]["tracks"][0]["track_name"], "Track 1")
        self.assertEqual(len(response.data["programs"][0]["tracks"][0]["presentations"]), 1)
        self.assertEqual(response.data["programs"][0]["tracks"][0]["presentations"][0]["team_id"], "CSE-314")

    def test_json_fields_serialized_correctly(self):
        """Test JSON fields serialized correctly."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            upper_bullet_points=["Point 1", "Point 2"],
            lower_bullet_points=["Lower 1"],
            expo_table=[{"time": "10:00 AM", "room": "A", "description": "Expo"}],
            reception_table=[{"time": "5:00 PM", "room": "B", "description": "Reception"}],
            is_published=True,
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["upper_bullet_points"], ["Point 1", "Point 2"])
        self.assertEqual(response.data["lower_bullet_points"], ["Lower 1"])
        self.assertEqual(len(response.data["expo_table"]), 1)
        self.assertEqual(len(response.data["reception_table"]), 1)

    def test_multiple_events_published_vs_unpublished_priority(self):
        """Test multiple events (published vs unpublished priority)."""
        # Create unpublished event first (older)
        unpublished = Event.objects.create(
            event_name="Unpublished",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            is_published=False,
        )
        # Create published event later
        published = Event.objects.create(
            event_name="Published",
            event_date=date(2024, 6, 16),
            event_time=time(10, 0),
            is_published=True,
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return published event even if it's newer
        self.assertEqual(response.data["event_name"], "Published")
