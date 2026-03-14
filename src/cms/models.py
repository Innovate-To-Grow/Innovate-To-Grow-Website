from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from core.models import ProjectControlModel

BLOCK_TYPE_CHOICES = [
    ("hero", "Hero Banner"),
    ("rich_text", "Rich Text"),
    ("faq_list", "FAQ List"),
    ("link_list", "Link List"),
    ("cta_group", "CTA Buttons"),
    ("image_text", "Image + Text"),
    ("notice", "Notice / Callout"),
    ("contact_info", "Contact Info"),
    ("google_sheet", "Google Sheet Embed"),
    ("section_group", "Section Group"),
    ("table", "Data Table"),
    ("numbered_list", "Numbered List"),
    ("proposal_cards", "Proposal Cards"),
    ("navigation_grid", "Navigation Grid"),
    ("schedule_grid", "Schedule Grid"),
]

BLOCK_TYPE_KEYS = {choice[0] for choice in BLOCK_TYPE_CHOICES}

# Required fields per block type (for validation)
BLOCK_SCHEMAS = {
    "hero": {"required": [], "optional": ["heading", "subheading", "image_url", "image_alt"]},
    "rich_text": {"required": ["body_html"], "optional": ["heading", "heading_level"]},
    "faq_list": {"required": ["items"], "optional": ["heading"]},
    "link_list": {"required": ["items"], "optional": ["heading", "style"]},
    "cta_group": {"required": ["items"], "optional": []},
    "image_text": {"required": ["body_html"], "optional": ["image_url", "image_alt", "image_position", "heading"]},
    "notice": {"required": ["body_html"], "optional": ["heading", "style"]},
    "contact_info": {"required": ["items"], "optional": ["heading"]},
    "google_sheet": {"required": ["sheet_source_slug"], "optional": ["sheet_view_slug", "display_mode", "heading"]},
    "section_group": {"required": ["sections"], "optional": ["heading"]},
    "table": {"required": ["columns", "rows"], "optional": ["heading"]},
    "numbered_list": {"required": ["items"], "optional": ["heading", "preamble_html"]},
    "proposal_cards": {"required": ["proposals"], "optional": ["heading", "footer_html"]},
    "navigation_grid": {"required": ["items"], "optional": ["heading"]},
    "schedule_grid": {"required": ["sheet_source_slug"], "optional": ["heading"]},
}


def validate_block_data(block_type, data):
    """Validate block data against its type schema."""
    if block_type not in BLOCK_SCHEMAS:
        raise ValidationError(f"Unknown block type: {block_type}")

    schema = BLOCK_SCHEMAS[block_type]
    for field in schema["required"]:
        if field not in data:
            raise ValidationError(f"Block type '{block_type}' requires field '{field}'.")


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
        if self.route and not self.route.startswith("/"):
            raise ValidationError({"route": "Route must start with '/'."})

    def save(self, *args, **kwargs):
        if self.status == "published" and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class CMSBlock(ProjectControlModel):
    """A content block within a CMS page."""

    page = models.ForeignKey(CMSPage, on_delete=models.CASCADE, related_name="blocks")
    block_type = models.CharField(max_length=30, choices=BLOCK_TYPE_CHOICES)
    sort_order = models.IntegerField(default=0)
    data = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    admin_label = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Label shown in admin for easier identification.",
    )

    class Meta:
        ordering = ["sort_order"]
        verbose_name = "Content Block"
        verbose_name_plural = "Content Blocks"
        indexes = [
            models.Index(fields=["page", "sort_order"]),
        ]

    def __str__(self):
        label = self.admin_label or self.get_block_type_display()
        return f"{label} (#{self.sort_order})"

    def clean(self):
        super().clean()
        validate_block_data(self.block_type, self.data)
