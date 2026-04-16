from django.db import models


class StyleSheet(models.Model):
    """Admin-managed CSS style sheets served to the frontend via the layout API.

    Each record holds a named block of CSS. Active sheets are concatenated
    in ``sort_order`` and delivered as a single string so the frontend injects
    one ``<style>`` tag covering the entire design system.
    """

    name = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Machine-readable identifier (e.g. 'global', 'cms-blocks', 'page-news').",
    )
    display_name = models.CharField(max_length=200)
    description = models.TextField(
        blank=True,
        default="",
        help_text="Internal note about what this sheet covers.",
    )
    css = models.TextField(
        blank=True,
        default="",
        help_text="Raw CSS injected into the page. Uses ITG design-token variables (--itg-*).",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(
        default=0,
        help_text="Lower numbers load first. Global sheets should be < 100, page sheets >= 100.",
    )

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Style Sheet"
        verbose_name_plural = "Style Sheets"

    def __str__(self):
        return self.display_name or self.name
