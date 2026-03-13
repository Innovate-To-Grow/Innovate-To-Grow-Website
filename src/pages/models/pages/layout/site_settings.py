from django.db import models


class SiteSettings(models.Model):
    """Singleton model for site-wide settings like homepage mode.

    This intentionally extends plain models.Model instead of ProjectControlModel.
    The pk=1 singleton pattern (enforced in save()) is incompatible with UUID
    primary keys, soft-delete, and versioning provided by ProjectControlModel.
    A single-row settings table does not need those features.
    """

    HOMEPAGE_MODES = [
        ("pre-event", "Pre-Event"),
        ("during-semester", "During Semester"),
        ("during-event", "During Event"),
        ("post-event", "Post-Event"),
    ]

    homepage_mode = models.CharField(
        max_length=20,
        choices=HOMEPAGE_MODES,
        default="post-event",
        help_text="Controls which homepage variant is displayed.",
    )

    homepage_route = models.CharField(
        max_length=100,
        default="/",
        blank=True,
        help_text='Route path to render as the homepage (e.g. "/event", "/about"). Use "/" for the default homepage.',
    )

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Settings"

    def save(self, *args, **kwargs):
        # Enforce singleton: always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
