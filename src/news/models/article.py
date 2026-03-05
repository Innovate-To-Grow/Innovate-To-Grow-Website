from django.db import models

from core.models import ProjectControlModel


class NewsArticle(ProjectControlModel):
    source = models.CharField(max_length=100, default="ucmerced", db_index=True)
    source_guid = models.CharField(max_length=500, unique=True)
    title = models.CharField(max_length=500)
    source_url = models.URLField(max_length=1000)
    summary = models.TextField(blank=True, default="")
    image_url = models.URLField(max_length=1000, blank=True, default="")
    author = models.CharField(max_length=255, blank=True, default="")
    published_at = models.DateTimeField(db_index=True)
    raw_payload = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["source", "source_guid"]),
        ]

    def __str__(self):
        return self.title
