from django.db import models
from django.utils.text import slugify

from core.models import ProjectControlModel


class Event(ProjectControlModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    date = models.DateField()
    time = models.TimeField()
    location = models.CharField(max_length=255)
    description = models.TextField()
    is_live = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date", "-time"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
