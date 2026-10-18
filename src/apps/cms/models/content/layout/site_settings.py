from django.db import models


def default_design_tokens():
    """Default design tokens: UC Merced School of Engineering subsite style.

    Values match the UC Merced Drupal subsite theme the original site used
    (innovatetogrow.ucmerced.edu): navy #0f2d52, header gold #dbaa00, menu gold
    #f8bd38, link hover / secondary blue #005487, sidebar rule #0f5479, footer
    bar #142d52 with a #d9a928 rule. Fonts are Open Sans for text and Khula for
    the site name, both loaded from Google Fonts in pages/index.html.
    """
    return {
        "colors": {
            "primary": "#0f2d52",
            "primary_hover": "#005487",
            "secondary": "#005487",
            "text": "#323336",
            "text_dark": "#333333",
            "text_secondary": "#555555",
            "bg_light": "#f2f2f2",
            "bg_panel": "#f7f7f7",
            "bg_page": "#ffffff",
            "white": "#fff",
            "border": "#dddddd",
            "border_table": "#cccccc",
            "border_input": "#cccccc",
            "accent_gold": "#dbaa00",
            "accent_gold_hover": "#be882c",
            "accent_bright": "#ffbf3c",
            "accent_menu": "#f8bd38",
            "sidebar_rule": "#0f5479",
            "footer_bar": "#142d52",
            "footer_bar_rule": "#d9a928",
            "highlight": "#fff6db",
            "tag_new": "#ffe9a8",
            "success": "#1e7b34",
            "disabled_text": "#6b6b6b",
            "disabled_bg": "#efefef",
            "disabled_border": "#d6d6d6",
            "footer_bg": "#e5e5e5",
            "error": "#9b1c1c",
            "error_light": "#b30000",
        },
        "typography": {
            "font_family_body": "'Open Sans', 'Segoe UI', Arial, sans-serif",
            "font_family_display": "'Khula', 'Open Sans', 'Segoe UI', Arial, sans-serif",
            "font_size_hero": "3rem",
            "font_size_h1": "2.25rem",
            "font_size_h2": "1.75rem",
            "font_size_h3": "1.5rem",
            "font_size_h4": "1.25rem",
            "font_size_lead": "1.125rem",
            "font_size_subtitle": "1.125rem",
            "font_size_body": "1rem",
            "font_size_meta": "1rem",
            "font_size_small": "0.875rem",
            "font_size_label": "1rem",
            "line_height_body": "1.5",
            "line_height_meta": "1.5",
            "line_height_heading": "1.5",
            "line_height_card": "1.4",
            "line_height_summary": "1.5",
        },
        "typography_mobile": {
            "font_size_hero_mobile": "2rem",
            "font_size_h1_mobile": "2.25rem",
            "font_size_h2_mobile": "1.75rem",
            "font_size_h3_mobile": "1.5rem",
            "font_size_h4_mobile": "1.25rem",
            "font_size_lead_mobile": "1.125rem",
            "font_size_table_mobile": "0.875rem",
        },
        "layout": {
            "page_max_width": "1170px",
            "page_narrow_width": "870px",
            "page_gutter": "1.5rem",
            "page_gutter_mobile": "1.25rem",
            "page_padding": "1rem 1.5rem 3rem",
            "page_padding_mobile": "1rem 1.25rem 2.5rem",
            "sidebar_width": "270px",
            "section_gap": "2rem",
            "list_indent": "1.5625rem",
        },
        "borders": {
            "radius_card": "0",
            "radius_button": "0",
            "radius_image": "0",
            "radius_input": "4px",
        },
        "effects": {
            "transition_fast": "0.2s",
            "transition_link": "0.15s",
            "shadow_card_hover": "0 2px 8px rgba(15, 45, 82, 0.12)",
            "shadow_header": "0 6px 6px -2px rgba(121, 121, 121, 0.67)",
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
        from apps.cms.models import CMSPage

        if self.homepage_page_id:
            selected_page = CMSPage.objects.filter(pk=self.homepage_page_id, status="published").first()
            if selected_page:
                return selected_page.route

        root_page = CMSPage.objects.filter(route="/", status="published").first()
        if root_page:
            return root_page.route

        return "/"
