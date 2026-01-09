import uuid

from django.core.exceptions import ValidationError
from django.db import models

from core.models.base import TimeStampedModel, SoftDeleteModel


def default_config():
    """Return a mutable default config dict."""
    return {}


class PageCascadingStyleSheets(models.Model):
    pass



class PageComponent(TimeStampedModel, SoftDeleteModel):
    """
    Reusable, ordered content block that can belong to a Page or HomePage.
    """

    # Technical identifier
    page_component_uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    page_component_name = models.CharField(
        max_length=255,
        help_text="Human readable name of the component."
    )

    # Basic Fields
    html_content = models.TextField(
        blank=True,
        default="",
        help_text="HTML content when component_type='html'.",
    )

    # TODO: Complete the page component logic
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
