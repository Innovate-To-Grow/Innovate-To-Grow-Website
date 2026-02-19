"""
Model tests for full Event hierarchy and relationships.
"""

from datetime import date, time

from django.test import TestCase

from ...models import Event, Presentation, Program, SpecialAward, Track, TrackWinner


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
        """Test full hierarchy creation (Event -> Program -> Track -> Presentation)."""
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
        self.assertIn(award, self.event.special_award_winners.all())
