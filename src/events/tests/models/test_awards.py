"""
Model tests for TrackWinner, SpecialAward models and hierarchy relationships.
"""

from datetime import date, time

from django.db import IntegrityError
from django.test import TestCase

from ...models import Event, SpecialAward, TrackWinner


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
