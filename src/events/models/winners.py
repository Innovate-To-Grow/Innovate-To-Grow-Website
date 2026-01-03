"""
Winner models for track winners and special awards.
"""

from django.db import models

from .event import Event


class TrackWinner(models.Model):
    """Winner for a specific track."""

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="track_winners", help_text="The event this winner belongs to."
    )
    track_name = models.CharField(max_length=255, help_text="Name of the track (matches Track.track_name).")
    winner_name = models.CharField(max_length=255, help_text="Name of the winning team/presentation.")

    def __str__(self):
        return f"{self.event.event_name} - {self.track_name}: {self.winner_name}"

    class Meta:
        unique_together = [["event", "track_name"]]
        verbose_name = "Track Winner"
        verbose_name_plural = "Track Winners"


class SpecialAward(models.Model):
    """Special award winner for a program."""

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="special_awards", help_text="The event this award belongs to."
    )
    program_name = models.CharField(max_length=255, help_text="Name of the program (matches Program.program_name).")
    award_winner = models.CharField(max_length=255, help_text="Name of the award winner.")

    def __str__(self):
        return f"{self.event.event_name} - {self.program_name}: {self.award_winner}"

    class Meta:
        unique_together = [["event", "program_name"]]
        verbose_name = "Special Award"
        verbose_name_plural = "Special Awards"
