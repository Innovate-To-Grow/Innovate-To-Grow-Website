"""
Model tests for Event model.
"""

from datetime import date, time

from django.test import TestCase

from ...models import Event


class EventModelTest(TestCase):
    """Test Event model."""

    def test_create_event_with_all_fields(self):
        """Test event creation with all fields."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            upper_bullet_points=["**Bold** point", "_Italic_ point"],
            lower_bullet_points=["Lower point 1", "Lower point 2"],
            expo_table=[{"time": "10:00 AM", "room": "Room A", "description": "Expo start"}],
            reception_table=[{"time": "5:00 PM", "room": "Room B", "description": "Reception"}],
            is_published=True,
        )
        self.assertEqual(event.event_name, "Test Event")
        self.assertEqual(event.event_date, date(2024, 6, 15))
        self.assertEqual(event.event_time, time(9, 0))
        self.assertEqual(len(event.upper_bullet_points), 2)
        self.assertEqual(len(event.lower_bullet_points), 2)
        self.assertEqual(len(event.expo_table), 1)
        self.assertEqual(len(event.reception_table), 1)
        self.assertTrue(event.is_published)
        self.assertIsNotNone(event.event_uuid)

    def test_event_uuid_auto_generation(self):
        """Test event_uuid is auto-generated."""
        event1 = Event.objects.create(
            event_name="Event 1",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        event2 = Event.objects.create(
            event_name="Event 2",
            event_date=date(2024, 6, 16),
            event_time=time(10, 0),
        )
        self.assertIsNotNone(event1.event_uuid)
        self.assertIsNotNone(event2.event_uuid)
        self.assertNotEqual(event1.event_uuid, event2.event_uuid)

    def test_event_default_values(self):
        """Test default values for event."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        self.assertEqual(event.upper_bullet_points, [])
        self.assertEqual(event.lower_bullet_points, [])
        self.assertEqual(event.expo_table, [])
        self.assertEqual(event.reception_table, [])
        self.assertFalse(event.is_published)

    def test_event_str_method(self):
        """Test Event __str__ method."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        self.assertEqual(str(event), "Test Event (2024-06-15)")

    def test_event_ordering(self):
        """Test event ordering by -event_date, then -created_at."""
        event1 = Event.objects.create(
            event_name="Event 1",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        event2 = Event.objects.create(
            event_name="Event 2",
            event_date=date(2024, 6, 16),
            event_time=time(10, 0),
        )
        event3 = Event.objects.create(
            event_name="Event 3",
            event_date=date(2024, 6, 15),
            event_time=time(11, 0),
        )
        events = list(Event.objects.all())
        # event2 should be first (newer date)
        self.assertEqual(events[0], event2)
        # event3 should be before event1 (same date, but created later)
        self.assertEqual(events[1], event3)
        self.assertEqual(events[2], event1)

    def test_event_json_field_handling(self):
        """Test JSON field handling."""
        event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            upper_bullet_points=["Point 1", "Point 2"],
            lower_bullet_points=["Lower 1"],
            expo_table=[{"time": "10:00 AM", "room": "A", "description": "Test"}],
            reception_table=[{"time": "5:00 PM", "room": "B", "description": "Reception"}],
        )
        # Reload from database
        event.refresh_from_db()
        self.assertEqual(event.upper_bullet_points, ["Point 1", "Point 2"])
        self.assertEqual(event.lower_bullet_points, ["Lower 1"])
        self.assertEqual(len(event.expo_table), 1)
        self.assertEqual(event.expo_table[0]["time"], "10:00 AM")
        self.assertEqual(len(event.reception_table), 1)
