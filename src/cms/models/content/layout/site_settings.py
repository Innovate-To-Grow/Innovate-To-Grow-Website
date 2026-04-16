from django.db import models


def default_design_tokens():
    """Default design tokens matching the original tokens.css values."""
    return {
        "colors": {
            "primary": "#0f2d52",
            "primary_hover": "#1a4a7a",
            "text": "#444",
            "text_dark": "#333",
            "text_secondary": "#666",
            "bg_light": "#f8f9fa",
            "bg_page": "#f9f9f9",
            "white": "#fff",
            "border": "#e0e0e0",
            "border_table": "#ccc",
            "accent_gold": "#daa520",
            "accent_gold_hover": "#c4941a",
            "accent_bright": "#FFBF3C",
            "error": "#c00",
            "error_light": "#b30000",
        },
        "typography": {
            "font_size_hero": "2.5rem",
            "font_size_h1": "2rem",
            "font_size_h2": "1.5rem",
            "font_size_h3": "1.25rem",
            "font_size_h4": "1.1rem",
            "font_size_lead": "1.1875rem",
            "font_size_subtitle": "1.125rem",
            "font_size_body": "1rem",
            "font_size_meta": "0.9375rem",
            "font_size_small": "0.875rem",
            "font_size_label": "0.8125rem",
            "line_height_body": "1.7",
            "line_height_meta": "1.6",
            "line_height_heading": "1.3",
            "line_height_card": "1.4",
            "line_height_summary": "1.5",
        },
        "typography_mobile": {
            "font_size_hero_mobile": "1.75rem",
            "font_size_h1_mobile": "1.5rem",
            "font_size_h2_mobile": "1.25rem",
            "font_size_h3_mobile": "1.125rem",
            "font_size_h4_mobile": "1rem",
            "font_size_lead_mobile": "1.0625rem",
            "font_size_table_mobile": "0.875rem",
        },
        "layout": {
            "page_max_width": "1200px",
            "page_narrow_width": "900px",
            "page_padding": "2rem 1rem",
            "page_padding_mobile": "1rem",
            "section_gap": "2rem",
            "list_indent": "1.5rem",
        },
        "borders": {
            "radius_card": "8px",
            "radius_button": "4px",
            "radius_image": "8px",
        },
        "effects": {
            "transition_fast": "0.2s",
            "transition_link": "0.15s",
            "shadow_card_hover": "0 4px 16px rgba(0, 0, 0, 0.12)",
        },
    }


class SiteSettings(models.Model):
    """Singleton model for site-wide settings like homepage selection.

    This intentionally extends plain models.Model instead of ProjectControlModel.
    The pk=1 singleton pattern (enforced in save()) is incompatible with UUID
    primary keys, soft-delete, and versioning provided by ProjectControlModel.
    A single-row settings table does not need those features.
    """

    homepage_page = models.ForeignKey(
        "cms.CMSPage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text='Published CMS page to render at "/". Leave blank to use the published "/" page.',
    )
    design_tokens = models.JSONField(
        default=default_design_tokens,
        help_text="Structured design tokens (colors, typography, layout) served to the frontend as CSS custom properties.",
    )

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Settings"

    # noinspection PyAttributeOutsideInit
    def save(self, *args, **kwargs):
        # Enforce singleton: always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def get_homepage_route(self):
        from cms.models import CMSPage

        if self.homepage_page_id:
            selected_page = CMSPage.objects.filter(pk=self.homepage_page_id, status="published").first()
            if selected_page:
                return selected_page.route

        root_page = CMSPage.objects.filter(route="/", status="published").first()
        if root_page:
            return root_page.route

        return "/"
