from django.db import models


class NewsSyncLog(models.Model):
    feed_source = models.ForeignKey(
        "pages.NewsFeedSource",
        on_delete=models.CASCADE,
        related_name="sync_logs",
    )
    started_at = models.DateTimeField()
    duration_seconds = models.FloatField(default=0)
    articles_created = models.PositiveIntegerField(default=0)
    articles_updated = models.PositiveIntegerField(default=0)
    errors_text = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(
                fields=["feed_source", "-started_at"],
                name="pages_synclog_source_started",
            ),
        ]

    def __str__(self):
        return f"{self.feed_source.name} - {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def has_errors(self):
        return bool(self.errors_text)
