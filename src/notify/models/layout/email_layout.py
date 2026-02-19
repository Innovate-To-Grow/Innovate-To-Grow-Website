from django.db import models

from core.models.base.control import ProjectControlModel


class EmailLayout(ProjectControlModel):
    """
    Stores the HTML wrapper layout for emails.
    """

    key = models.SlugField(
        max_length=64,
        unique=True,
        help_text="Unique key used to select this layout (e.g. 'base').",
    )
    name = models.CharField(
        max_length=128,
        help_text="Human-readable name for this layout.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description to help admins understand this layout.",
    )
    html_template = models.TextField(
        help_text="Django template HTML. Use {{ body_html }}, {{ subject }}, {{ brand_name }}, etc.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only active layouts are used for sending.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Use this layout when no specific layout is selected.",
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["key"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_default"]),
        ]
        verbose_name = "Email Layout"
        verbose_name_plural = "Email Layouts"

    def __str__(self) -> str:
        return f"{self.name} ({self.key})"
