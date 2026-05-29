from django.db import models

from core.models import ProjectControlModel


class NewsFeedSource(ProjectControlModel):
    name = models.CharField(max_length=200)
    feed_url = models.URLField(max_length=1000)
    source_key = models.SlugField(max_length=100, unique=True, default="ucmerced")
    is_active = models.BooleanField(default=True, db_index=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_created = models.PositiveIntegerField(default=0)
    last_sync_updated = models.PositiveIntegerField(default=0)
    last_sync_errors = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
