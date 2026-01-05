from django.core.exceptions import ValidationError
from django.db import models

from core.models.base import OrderedModel, TimeStampedModel


def default_config():
    """Return a mutable default config dict."""
    return {}


class PageComponent(TimeStampedModel, OrderedModel):
    """
    Reusable, ordered content block that can belong to a Page or HomePage.

    Supported component types (extensible):
    - html: raw HTML content (current focus)
    - form: reference to a form component (future use)
    - google_sheet: embedded Google Sheet (future use)
    - sheet: internal sheet/table data (future use)
    """

    COMPONENT_TYPE_HTML = "html"
    COMPONENT_TYPE_FORM = "form"
    COMPONENT_TYPE_GOOGLE_SHEET = "google_sheet"
    COMPONENT_TYPE_SHEET = "sheet"

    COMPONENT_TYPE_CHOICES = [
        (COMPONENT_TYPE_HTML, "HTML"),
        (COMPONENT_TYPE_FORM, "Form"),
        (COMPONENT_TYPE_GOOGLE_SHEET, "Google Sheet"),
        (COMPONENT_TYPE_SHEET, "Sheet"),
    ]

    # Parent relations (exactly one must be set)
    page = models.ForeignKey(
        "pages.Page",
        related_name="components",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Parent Page (set for standard pages).",
    )
    home_page = models.ForeignKey(
        "pages.HomePage",
        related_name="components",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Parent HomePage (set for homepage versions).",
    )

    # Component definition
    component_type = models.CharField(
        max_length=50,
        choices=COMPONENT_TYPE_CHOICES,
        default=COMPONENT_TYPE_HTML,
        help_text="Type of component to render.",
    )
    html_content = models.TextField(
        blank=True,
        default="",
        help_text="HTML content when component_type='html'.",
    )
    css_file = models.FileField(
        upload_to="page_components/css/",
        blank=True,
        null=True,
        help_text="Optional CSS file to load for this component.",
    )
    css_code = models.TextField(
        blank=True,
        default="",
        help_text="Inline CSS applied to this component (scoped by renderer).",
    )
    js_code = models.TextField(
        blank=True,
        default="",
        help_text="JavaScript code to execute within this component (runs in isolated scope).",
    )
    config = models.JSONField(
        default=default_config,
        blank=True,
        null=True,
        help_text="Structured config for non-HTML component types.",
    )

    # ------------------------------ Validation ------------------------------

    def clean(self):
        super().clean()
        if bool(self.page) == bool(self.home_page):
            raise ValidationError("Component must belong to exactly one of page or home page.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    # ------------------------------ Helpers ------------------------------

    @property
    def parent(self):
        """Return the assigned parent object (Page or HomePage)."""
        return self.page or self.home_page

    def __str__(self) -> str:
        parent_label = self.page.slug if self.page else (self.home_page.name if self.home_page else "unassigned")
        return f"{self.component_type} component for {parent_label} (order {self.order})"

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Page Component"
        verbose_name_plural = "Page Components"
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(page__isnull=False) & models.Q(home_page__isnull=True))
                    | (models.Q(page__isnull=True) & models.Q(home_page__isnull=False))
                ),
                name="pages_pagecomponent_single_parent",
            ),
        ]
