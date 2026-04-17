import re

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from core.models import ProjectControlModel

from .cms_page import CMSPage

EMBED_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class CMSEmbedWidget(ProjectControlModel):
    """A named iframe-embeddable bundle of blocks on a CMSPage."""

    page = models.ForeignKey(
        CMSPage,
        on_delete=models.CASCADE,
        related_name="embed_widgets",
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        help_text="Globally unique kebab-case identifier used in the embed URL.",
    )
    admin_label = models.CharField(max_length=200, blank=True, default="")
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

        refs = self.block_sort_orders or []
        if not isinstance(refs, list):
            raise ValidationError({"block_sort_orders": "Must be a list of integers."})

        if self.page_id:
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
