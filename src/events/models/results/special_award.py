"""Special award model."""

from django.db import models

from core.models.base.control import ProjectControlModel


class SpecialAward(ProjectControlModel):
    """Special award for a program."""

    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="special_award_winners",
        help_text="The event this award belongs to.",
    )
    program_name = models.CharField(
        max_length=255,
        help_text="Name of the program.",
    )
    award_winner = models.CharField(
        max_length=255,
        help_text="Name of the award winner.",
    )

    def __str__(self):
        return f"{self.event.event_name} - {self.program_name}: {self.award_winner}"

    class Meta:
        unique_together = [["event", "program_name"]]
        verbose_name = "Special Award"
        verbose_name_plural = "Special Awards"
