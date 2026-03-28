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
    is_current = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-year", "-season"]
        unique_together = [["year", "season"]]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        self.label = f"{self.year}-{self.season} {self.get_season_display()}"

        if self.is_current and not self.is_published:
            self.is_published = True

        super().save(*args, **kwargs)

        # Clear is_current on all other semesters, but only when is_current was actually persisted
        update_fields = kwargs.get("update_fields")
        if self.is_current and (update_fields is None or "is_current" in update_fields):
            Semester.objects.exclude(pk=self.pk).filter(is_current=True).update(is_current=False)

    @classmethod
    def current_pk_subquery(cls):
        """Return a subquery for the current semester PK, with fallback to newest published."""
        qs = cls.objects.filter(is_published=True, is_current=True).values("pk")[:1]
        if not qs.exists():
            qs = cls.objects.filter(is_published=True).values("pk")[:1]
        return qs
