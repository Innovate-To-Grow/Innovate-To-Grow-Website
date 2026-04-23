import re

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from core.models import ProjectControlModel

from .cms_page import CMSPage

EMBED_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

WIDGET_TYPE_BLOCKS = "blocks"
WIDGET_TYPE_APP_ROUTE = "app_route"
WIDGET_TYPE_CHOICES = [
    (WIDGET_TYPE_BLOCKS, "CMS Page Blocks"),
    (WIDGET_TYPE_APP_ROUTE, "App Route (interactive page)"),
]


class CMSEmbedWidget(ProjectControlModel):
    """A named iframe-embeddable widget — either a bundle of CMSPage blocks or an app route."""

    widget_type = models.CharField(
        max_length=16,
        choices=WIDGET_TYPE_CHOICES,
        default=WIDGET_TYPE_BLOCKS,
        help_text="Whether this widget embeds CMS blocks or a full app-route page (e.g. /schedule).",
    )
    page = models.ForeignKey(
        CMSPage,
        on_delete=models.CASCADE,
        related_name="embed_widgets",
        null=True,
        blank=True,
        help_text="Source page for 'blocks' widgets. Leave blank for 'app_route' widgets.",
    )
    app_route = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="App route path (e.g. /schedule) for 'app_route' widgets.",
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        help_text="Globally unique kebab-case identifier used in the embed URL.",
    )
    admin_label = models.CharField(max_length=200, blank=True, default="")
    hide_section_titles = models.BooleanField(
        default=False,
        help_text="Hide `.section-title` headings when this widget renders inside the embed iframe.",
    )
    block_sort_orders = models.JSONField(
        default=list,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text="List of CMSBlock.sort_order values to include, in declared order.",
    )

    class Meta:
        db_table = "cms_cmsembedwidget"
        ordering = ["page__title", "slug"]
        verbose_name = "CMS Embed Widget"
        verbose_name_plural = "CMS Embed Widgets"
        indexes = [models.Index(fields=["slug"])]

    def __str__(self):
        return f"{self.admin_label or self.slug} ({self.slug})"

    def clean(self):
        super().clean()
        slug = (self.slug or "").strip().lower()
        if not slug or not EMBED_SLUG_RE.match(slug):
            raise ValidationError({"slug": "Slug must be kebab-case: lowercase letters, digits, and hyphens only."})
        self.slug = slug

        if self.widget_type == WIDGET_TYPE_APP_ROUTE:
            self._clean_app_route()
            self.block_sort_orders = []
            return

        self._clean_blocks()

    def _clean_app_route(self):
        from cms.app_routes import APP_ROUTES

        route = (self.app_route or "").strip()
        if not route:
            raise ValidationError({"app_route": "App route is required for app_route widgets."})
        allowed = {entry["url"] for entry in APP_ROUTES}
        if route not in allowed:
            raise ValidationError({"app_route": f"Unknown app route: {route}."})
        self.app_route = route

    def _clean_blocks(self):
        self.app_route = ""
        if not self.page_id:
            raise ValidationError({"page": "A source page is required for blocks widgets."})

        refs = self.block_sort_orders or []
        if not isinstance(refs, list):
            raise ValidationError({"block_sort_orders": "Must be a list of integers."})

        valid = set(self.page.blocks.values_list("sort_order", flat=True))
        cleaned: list[int] = []
        for ref in refs:
            try:
                i = int(ref)
            except (TypeError, ValueError):
                continue
            if i in valid and i not in cleaned:
                cleaned.append(i)
        if not cleaned:
            raise ValidationError({"block_sort_orders": "Must reference at least one existing block on the page."})
        self.block_sort_orders = sorted(cleaned)
