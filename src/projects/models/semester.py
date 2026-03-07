from django.db import models

from core.models import ProjectControlModel


class Semester(ProjectControlModel):
    class Season(models.IntegerChoices):
        SPRING = 1, "Spring"
        FALL = 2, "Fall"

    year = models.PositiveIntegerField(db_index=True)
    season = models.PositiveSmallIntegerField(choices=Season.choices, db_index=True)
    label = models.CharField(max_length=50, blank=True, default="")
    is_published = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-year", "-season"]
        unique_together = [["year", "season"]]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        self.label = f"{self.year}-{self.season} {self.get_season_display()}"
        super().save(*args, **kwargs)
