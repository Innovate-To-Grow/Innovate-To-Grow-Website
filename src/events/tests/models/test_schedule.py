"""
Model tests for Program and Track models.
"""

from datetime import date, time

from django.db import IntegrityError
from django.test import TestCase

from ...models import Event, Program, Track


class ProgramModelTest(TestCase):
    """Test Program model."""

    def setUp(self):
        """Set up test data."""
        self.event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

    def test_program_creation_linked_to_event(self):
        """Test program creation linked to event."""
        program = Program.objects.create(
            event=self.event,
            program_name="CSE Program",
            order=1,
        )
        self.assertEqual(program.event, self.event)
        self.assertEqual(program.program_name, "CSE Program")
        self.assertEqual(program.order, 1)
        self.assertIn(program, self.event.programs.all())

    def test_program_unique_together_constraint(self):
        """Test unique_together constraint (event + program_name)."""
        Program.objects.create(
            event=self.event,
            program_name="CSE Program",
        )
        # Try to create duplicate
        with self.assertRaises(IntegrityError):
            Program.objects.create(
                event=self.event,
                program_name="CSE Program",
            )

    def test_program_ordering(self):
        """Test program ordering by order, then id."""
        program2 = Program.objects.create(event=self.event, program_name="Program 2", order=2)
        program1 = Program.objects.create(event=self.event, program_name="Program 1", order=1)
        program3 = Program.objects.create(event=self.event, program_name="Program 3", order=1)
        programs = list(Program.objects.filter(event=self.event))
        self.assertEqual(programs[0], program1)
        self.assertEqual(programs[1], program3)
        self.assertEqual(programs[2], program2)

    def test_program_cascade_delete(self):
        """Test cascade delete when event is deleted."""
        program = Program.objects.create(
            event=self.event,
            program_name="CSE Program",
        )
        program_id = program.id
        self.event.delete()
        self.assertFalse(Program.objects.filter(id=program_id).exists())

    def test_program_str_method(self):
        """Test Program __str__ method."""
        program = Program.objects.create(
            event=self.event,
            program_name="CSE Program",
        )
        self.assertEqual(str(program), "Test Event - CSE Program")


class TrackModelTest(TestCase):
    """Test Track model."""

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

    def test_track_creation_with_start_time(self):
        """Test track creation with start_time."""
        track = Track.objects.create(
            program=self.program,
            track_name="Track 1",
            room="Room A",
            start_time=time(13, 0),
            order=1,
        )
        self.assertEqual(track.start_time, time(13, 0))
        self.assertEqual(track.track_name, "Track 1")
        self.assertEqual(track.room, "Room A")

    def test_track_creation_without_start_time(self):
        """Test track creation without start_time (null)."""
        track = Track.objects.create(
            program=self.program,
            track_name="Track 1",
            room="Room A",
            start_time=None,
        )
        self.assertIsNone(track.start_time)

    def test_track_unique_together_constraint(self):
        """Test unique_together constraint (program + track_name)."""
        Track.objects.create(
            program=self.program,
            track_name="Track 1",
            room="Room A",
        )
        # Try to create duplicate
        with self.assertRaises(IntegrityError):
            Track.objects.create(
                program=self.program,
                track_name="Track 1",
                room="Room B",
            )

    def test_track_ordering(self):
        """Test track ordering by order, then id."""
        track2 = Track.objects.create(program=self.program, track_name="Track 2", room="A", order=2)
        track1 = Track.objects.create(program=self.program, track_name="Track 1", room="B", order=1)
        tracks = list(Track.objects.filter(program=self.program))
        self.assertEqual(tracks[0], track1)
        self.assertEqual(tracks[1], track2)

    def test_track_cascade_delete(self):
        """Test cascade delete when program is deleted."""
        track = Track.objects.create(
            program=self.program,
            track_name="Track 1",
            room="Room A",
        )
        track_id = track.id
        self.program.delete()
        self.assertFalse(Track.objects.filter(id=track_id).exists())

    def test_track_str_method(self):
        """Test Track __str__ method."""
        track = Track.objects.create(
            program=self.program,
            track_name="Track 1",
            room="Room A",
        )
        self.assertEqual(str(track), "CSE Program - Track 1 (Room A)")
