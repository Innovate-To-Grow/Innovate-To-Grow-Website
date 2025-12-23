from django.db import models


class HomePage(models.Model):
    """Home page model supporting multiple versions with one active at a time."""

    name = models.CharField(
        max_length=200,
        help_text="Internal name to identify this home page version"
    )
    body = models.TextField(
        blank=True,
        help_text="Rich text content (HTML)"
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Only one home page can be active at a time"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Home Page"
        verbose_name_plural = "Home Pages"

    def save(self, *args, **kwargs):
        # If this home page is being set as active, deactivate all others
        if self.is_active:
            HomePage.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        status = " (Active)" if self.is_active else ""
        return f"{self.name}{status}"

    @classmethod
    def get_active(cls):
        """Get the currently active home page."""
        return cls.objects.filter(is_active=True).first()

