"""
Model tests for Presentation model.
"""

from datetime import date, time

from django.db import IntegrityError
from django.test import TestCase

from ...models import Event, Presentation, Program, Track


class PresentationModelTest(TestCase):
    """Test Presentation model."""

    def setUp(self):
        """Set up test data."""
        self.event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )
        self.program = Program.objects.create(
            event=self.event,
            program_name="CSE Program",
        )
        self.track = Track.objects.create(
            program=self.program,
            track_name="Track 1",
            room="Room A",
        )

    def test_presentation_creation_with_all_fields(self):
        """Test presentation creation with all fields."""
        presentation = Presentation.objects.create(
            track=self.track,
            order=1,
            team_id="CSE-314",
            team_name="Team Alpha",
            project_title="Amazing Project",
            organization="Organization A",
        )
        self.assertEqual(presentation.order, 1)
        self.assertEqual(presentation.team_id, "CSE-314")
        self.assertEqual(presentation.team_name, "Team Alpha")
        self.assertEqual(presentation.project_title, "Amazing Project")
        self.assertEqual(presentation.organization, "Organization A")

    def test_presentation_creation_with_null_team_fields_for_breaks(self):
        """Test presentation creation with null team_id/team_name (for breaks)."""
        presentation = Presentation.objects.create(
            track=self.track,
            order=1,
            team_id=None,
            team_name=None,
            project_title="Break",
            organization=None,
        )
        self.assertIsNone(presentation.team_id)
        self.assertIsNone(presentation.team_name)
        self.assertEqual(presentation.project_title, "Break")

    def test_presentation_unique_together_constraint(self):
        """Test unique_together constraint (track + order)."""
        Presentation.objects.create(
            track=self.track,
            order=1,
            project_title="Presentation 1",
        )
        # Try to create duplicate
        with self.assertRaises(IntegrityError):
            Presentation.objects.create(
                track=self.track,
                order=1,
                project_title="Presentation 2",
            )

    def test_presentation_order_minimum_validation(self):
        """Test order minimum value validation (must be >= 1)."""
        # This is enforced at the database level via MinValueValidator
        presentation = Presentation.objects.create(
            track=self.track,
            order=1,
            project_title="Valid",
        )
        self.assertEqual(presentation.order, 1)

    def test_presentation_cascade_delete(self):
        """Test cascade delete when track is deleted."""
        presentation = Presentation.objects.create(
            track=self.track,
            order=1,
            project_title="Test",
        )
        presentation_id = presentation.id
        self.track.delete()
        self.assertFalse(Presentation.objects.filter(id=presentation_id).exists())

    def test_presentation_str_method_with_team_name(self):
        """Test Presentation __str__ method with team_name."""
        presentation = Presentation.objects.create(
            track=self.track,
            order=1,
            team_name="Team Alpha",
            project_title="Amazing Project",
        )
        self.assertEqual(str(presentation), "Track 1 #1: Team Alpha - Amazing Project")

    def test_presentation_str_method_without_team_name(self):
        """Test Presentation __str__ method without team_name (break)."""
        presentation = Presentation.objects.create(
            track=self.track,
            order=1,
            project_title="Break",
        )
        self.assertEqual(str(presentation), "Track 1 #1: Break - Break")
