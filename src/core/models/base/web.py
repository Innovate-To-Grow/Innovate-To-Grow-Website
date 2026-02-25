from django.db import models


class SiteMaintenanceControl(models.Model):
    """
    Singleton model to control site-wide maintenance mode.

    When `is_maintenance` is True, the health check endpoint returns
    maintenance status and the frontend displays a maintenance page
    with the configured message.
    """

    is_maintenance = models.BooleanField(
        default=False,
        verbose_name="Maintenance Mode",
        help_text="Enable to put the site into maintenance mode.",
    )
    message = models.TextField(
        blank=True,
        default="We are performing scheduled maintenance. Please try again shortly.",
        verbose_name="Maintenance Message",
        help_text="Message displayed to users during maintenance.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Maintenance Control"
        verbose_name_plural = "Site Maintenance Control"

    def __str__(self):
        status = "ON" if self.is_maintenance else "OFF"
        return f"Maintenance Mode: {status}"

    def save(self, *args, **kwargs):
        # Enforce singleton: always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Load the singleton instance, creating it with defaults if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
