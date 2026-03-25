from django.db import models

from core.models import ProjectControlModel


class Sponsor(ProjectControlModel):
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="sponsors/logos/", blank=True)
    website = models.URLField(max_length=1000, blank=True)
    year = models.PositiveIntegerField(db_index=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-year", "display_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.year})"
