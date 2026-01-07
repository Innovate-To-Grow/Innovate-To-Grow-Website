from django.db import models
from django.core.exceptions import ValidationError


class SiteSettings(models.Model):
    """
    Singleton model for site-wide settings.
    Only one instance should exist at a time.
    """

    HOME_PAGE_MODE_CHOICES = [
        ('pre_event', 'Pre Event'),
        ('during_semester', 'During Semester'),
        ('event', 'Event'),
    ]

    home_page_mode = models.CharField(
        max_length=20,
        choices=HOME_PAGE_MODE_CHOICES,
        default='pre_event',
        help_text="Select which home page variant to display"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"
        ordering = ['-updated_at']

    def __str__(self):
        return f"Site Settings ({self.get_home_page_mode_display()})"

    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        if not self.pk and SiteSettings.objects.exists():
            raise ValidationError("Only one SiteSettings instance is allowed.")
        super().save(*args, **kwargs)

    @classmethod
    def get_instance(cls):
        """Get or create the singleton SiteSettings instance."""
        instance, created = cls.objects.get_or_create(pk=1)
        return instance



