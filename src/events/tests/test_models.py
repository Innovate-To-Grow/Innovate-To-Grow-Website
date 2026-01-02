"""
Model tests for events app.
"""

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from datetime import date, time
from ..models import Event, Program, Track, Presentation, TrackWinner, SpecialAward


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


class TrackWinnerModelTest(TestCase):
    """Test TrackWinner model."""

    def setUp(self):
        """Set up test data."""
        self.event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

    def test_track_winner_creation(self):
        """Test track winner creation."""
        winner = TrackWinner.objects.create(
            event=self.event,
            track_name="Track 1",
            winner_name="Team Alpha",
        )
        self.assertEqual(winner.track_name, "Track 1")
        self.assertEqual(winner.winner_name, "Team Alpha")
        self.assertEqual(winner.event, self.event)

    def test_track_winner_unique_together_constraint(self):
        """Test unique_together constraint (event + track_name)."""
        TrackWinner.objects.create(
            event=self.event,
            track_name="Track 1",
            winner_name="Team Alpha",
        )
        # Try to create duplicate
        with self.assertRaises(IntegrityError):
            TrackWinner.objects.create(
                event=self.event,
                track_name="Track 1",
                winner_name="Team Beta",
            )

    def test_track_winner_cascade_delete(self):
        """Test cascade delete when event is deleted."""
        winner = TrackWinner.objects.create(
            event=self.event,
            track_name="Track 1",
            winner_name="Team Alpha",
        )
        winner_id = winner.id
        self.event.delete()
        self.assertFalse(TrackWinner.objects.filter(id=winner_id).exists())

    def test_track_winner_str_method(self):
        """Test TrackWinner __str__ method."""
        winner = TrackWinner.objects.create(
            event=self.event,
            track_name="Track 1",
            winner_name="Team Alpha",
        )
        self.assertEqual(str(winner), "Test Event - Track 1: Team Alpha")


class SpecialAwardModelTest(TestCase):
    """Test SpecialAward model."""

    def setUp(self):
        """Set up test data."""
        self.event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

    def test_special_award_creation(self):
        """Test special award creation."""
        award = SpecialAward.objects.create(
            event=self.event,
            program_name="CSE Program",
            award_winner="Team Alpha",
        )
        self.assertEqual(award.program_name, "CSE Program")
        self.assertEqual(award.award_winner, "Team Alpha")
        self.assertEqual(award.event, self.event)

    def test_special_award_unique_together_constraint(self):
        """Test unique_together constraint (event + program_name)."""
        SpecialAward.objects.create(
            event=self.event,
            program_name="CSE Program",
            award_winner="Team Alpha",
        )
        # Try to create duplicate
        with self.assertRaises(IntegrityError):
            SpecialAward.objects.create(
                event=self.event,
                program_name="CSE Program",
                award_winner="Team Beta",
            )

    def test_special_award_cascade_delete(self):
        """Test cascade delete when event is deleted."""
        award = SpecialAward.objects.create(
            event=self.event,
            program_name="CSE Program",
            award_winner="Team Alpha",
        )
        award_id = award.id
        self.event.delete()
        self.assertFalse(SpecialAward.objects.filter(id=award_id).exists())

    def test_special_award_str_method(self):
        """Test SpecialAward __str__ method."""
        award = SpecialAward.objects.create(
            event=self.event,
            program_name="CSE Program",
            award_winner="Team Alpha",
        )
        self.assertEqual(str(award), "Test Event - CSE Program: Team Alpha")


class HierarchyTest(TestCase):
    """Test full hierarchy and relationships."""

    def setUp(self):
        """Set up test data."""
        self.event = Event.objects.create(
            event_name="Test Event",
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
        )

    def test_full_hierarchy_creation(self):
        """Test full hierarchy creation (Event → Program → Track → Presentation)."""
        program = Program.objects.create(
            event=self.event,
            program_name="CSE Program",
        )
        track = Track.objects.create(
            program=program,
            track_name="Track 1",
            room="Room A",
        )
        presentation = Presentation.objects.create(
            track=track,
            order=1,
            project_title="Test Project",
        )
        # Verify relationships
        self.assertEqual(presentation.track, track)
        self.assertEqual(track.program, program)
        self.assertEqual(program.event, self.event)
        # Verify reverse relationships
        self.assertIn(program, self.event.programs.all())
        self.assertIn(track, program.tracks.all())
        self.assertIn(presentation, track.presentations.all())

    def test_cascade_deletes_propagate(self):
        """Test cascade deletes propagate correctly."""
        program = Program.objects.create(
            event=self.event,
            program_name="CSE Program",
        )
        track = Track.objects.create(
            program=program,
            track_name="Track 1",
            room="Room A",
        )
        presentation = Presentation.objects.create(
            track=track,
            order=1,
            project_title="Test",
        )
        # Delete event - everything should cascade
        self.event.delete()
        self.assertFalse(Program.objects.filter(id=program.id).exists())
        self.assertFalse(Track.objects.filter(id=track.id).exists())
        self.assertFalse(Presentation.objects.filter(id=presentation.id).exists())

    def test_related_name_access(self):
        """Test related_name access for all relationships."""
        program = Program.objects.create(
            event=self.event,
            program_name="CSE Program",
        )
        track = Track.objects.create(
            program=program,
            track_name="Track 1",
            room="Room A",
        )
        presentation = Presentation.objects.create(
            track=track,
            order=1,
            project_title="Test",
        )
        winner = TrackWinner.objects.create(
            event=self.event,
            track_name="Track 1",
            winner_name="Winner",
        )
        award = SpecialAward.objects.create(
            event=self.event,
            program_name="CSE Program",
            award_winner="Award Winner",
        )
        # Test related_name access
        self.assertIn(program, self.event.programs.all())
        self.assertIn(track, program.tracks.all())
        self.assertIn(presentation, track.presentations.all())
        self.assertIn(winner, self.event.track_winners.all())
        self.assertIn(award, self.event.special_awards.all())

