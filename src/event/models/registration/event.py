from django.db import models
from django.utils.text import slugify

from core.models import ProjectControlModel


class Event(ProjectControlModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    date = models.DateField()
    location = models.CharField(max_length=255)
    description = models.TextField()
    is_live = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
        update_fields = kwargs.get("update_fields")
        if self.is_live and (update_fields is None or "is_live" in update_fields):
            Event.objects.exclude(pk=self.pk).filter(is_live=True).update(is_live=False)
