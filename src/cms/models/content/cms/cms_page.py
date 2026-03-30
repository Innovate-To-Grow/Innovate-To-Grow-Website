import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import ProjectControlModel

ROUTE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*$")


def normalize_cms_route(route):
    """Normalize CMS route paths to a canonical leading-slash/no-trailing-slash form."""
    route = (route or "").strip()
    if not route:
        return "/"

    segments = [segment.strip() for segment in route.split("/") if segment.strip()]
    if not segments:
        return "/"

    return "/" + "/".join(segments)


def validate_cms_route(route):
    """Validate a normalized CMS route."""
    normalized = normalize_cms_route(route)

    if normalized == "/":
        return normalized

    for segment in normalized.strip("/").split("/"):
        if not ROUTE_SEGMENT_RE.fullmatch(segment):
            raise ValidationError(
                "Each path segment must use letters, numbers, hyphens, or underscores only.",
            )

    return normalized


class CMSPage(ProjectControlModel):
    """A CMS-managed page. One record per frontend route."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="Stable identifier for import/export. Do not change after publishing.",
    )
    route = models.CharField(
        max_length=200,
        unique=True,
        help_text="Frontend route path, e.g. '/about'. Must start with '/'.",
    )
    title = models.CharField(max_length=300)
    meta_description = models.TextField(blank=True, default="")

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft", db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)

    page_css_class = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="CSS class for the page wrapper div, e.g. 'about-page'.",
    )
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "cms_cmspage"
        ordering = ["sort_order", "title"]
        verbose_name = "CMS Page"
        verbose_name_plural = "CMS Pages"
        indexes = [
            models.Index(fields=["route", "status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.route})"

    def clean(self):
        super().clean()
        try:
            self.route = validate_cms_route(self.route)
        except ValidationError as exc:
            raise ValidationError({"route": exc.messages})

    def save(self, *args, **kwargs):
        self.route = normalize_cms_route(self.route)
        if self.status == "published" and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)
