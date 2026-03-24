from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.models import ProjectControlModel


class SyncDirection(models.TextChoices):
    PULL = "pull", "Pull (Sheet → DB)"
    PUSH = "push", "Push (DB → Sheet)"
    BOTH = "both", "Both (Manual choice per operation)"


class SheetLink(ProjectControlModel):
    """
    Links a Django model to a Google Sheet for bi-directional sync.

    Column mapping uses Django __ syntax for FK fields:
        {
            "Year": "semester__year",
            "Season": "semester__season",
            "Class": "class_code",
            "Team#": "team_number"
        }

    The sync engine groups __ fields by FK prefix and resolves them
    via get() or get_or_create() based on fk_config.
    """

    name = models.CharField(
        max_length=200,
        help_text='Human-readable label, e.g. "Fall 2025 Projects"',
    )
    account = models.ForeignKey(
        "sheets.SheetsAccount",
        on_delete=models.PROTECT,
        related_name="links",
    )

    # Google Sheet coordinates
    spreadsheet_id = models.CharField(
        max_length=200,
        help_text="Google Sheets spreadsheet ID",
    )
    sheet_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Tab/sheet name within the spreadsheet",
    )
    range_a1 = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Optional A1 range within the tab, e.g. 'A1:L100'",
    )

    # Target model (generic via ContentType)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Django model to sync with this sheet",
    )

    # Column mapping: {"Sheet Header": "model_field"} or {"Header": "fk__field"}
    column_mapping = models.JSONField(
        default=dict,
        help_text=(
            "Map sheet headers to model fields. Use __ for FK fields: "
            '{"Year": "semester__year", "Class": "class_code"}. '
            'Use "__skip__" to ignore a column.'
        ),
    )

    # FK resolution config
    fk_config = models.JSONField(
        default=dict,
        blank=True,
        help_text=('FK behavior config: {"semester": {"create_if_missing": true, "defaults": {"is_published": true}}}'),
    )

    # Lookup fields for upsert matching
    lookup_fields = models.JSONField(
        default=list,
        help_text=(
            'Model field names forming the unique key for upserts, e.g. ["semester", "team_number", "project_title"]'
        ),
    )

    # Sync configuration
    sync_direction = models.CharField(
        max_length=4,
        choices=SyncDirection.choices,
        default=SyncDirection.PULL,
    )
    row_transform_hook = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "Dotted path to a Python function for custom row transforms "
            "before FK resolution, e.g. 'projects.services.hooks.resolve_project_row'"
        ),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Sheet Link"
        verbose_name_plural = "Sheet Links"

    def __str__(self):
        model_label = self.content_type.model_class().__name__ if self.content_type_id else "?"
        return f"{self.name} ({model_label})"

    def get_model_class(self):
        """Return the linked Django model class."""
        return self.content_type.model_class()

    def get_sheet_range(self):
        """Build the full A1 range reference for the Google Sheets API."""
        if self.sheet_name and self.range_a1:
            return f"{self.sheet_name}!{self.range_a1}"
        return self.sheet_name or self.range_a1 or ""
