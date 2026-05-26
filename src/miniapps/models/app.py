from django.core.validators import RegexValidator
from django.db import models

from core.models import ProjectControlModel


class MiniApp(ProjectControlModel):
    """A managed app route with admin-authored JS/HTML/CSS code."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    url_path = models.CharField(
        max_length=200,
        unique=True,
        validators=[
            RegexValidator(
                r"^/[a-z0-9][a-z0-9\-/]*$", "Must start with / and contain only lowercase, digits, hyphens, slashes."
            )
        ],
        help_text="Frontend URL path, e.g. /news or /my-tool",
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True, help_text="Used in API URLs: /miniapps/<slug>/...")
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=50, blank=True, default="", help_text="Material icon name")

    embeddable = models.BooleanField(default=True, help_text="Whether this app can be rendered in /_embed/ iframes")
    url_prefix_match = models.BooleanField(
        default=False, help_text="Match any path starting with url_path (e.g. /news also matches /news/123)"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")

    html_code = models.TextField(blank=True, default="", verbose_name="HTML")
    js_code = models.TextField(blank=True, default="", verbose_name="JavaScript")
    css_code = models.TextField(blank=True, default="", verbose_name="CSS")

    class Meta:
        ordering = ["title"]
        verbose_name = "Mini App"
        verbose_name_plural = "Mini Apps"

    def __str__(self):
        return f"{self.title} ({self.url_path})"
