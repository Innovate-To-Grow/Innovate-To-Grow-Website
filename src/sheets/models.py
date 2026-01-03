from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Sheet(TimeStampedModel):
    """Top-level sheet containing tabs and metadata."""

    name = models.CharField(
        max_length=255,
        help_text="Name of the sheet for internal reference.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of what this sheet contains.",
    )
    columns = models.JSONField(
        default=list,
        blank=True,
        help_text="List of column definitions. Each should have 'name' and 'key'.",
    )
    data = models.JSONField(
        default=list,
        blank=True,
        help_text="List of row data matching the column keys.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_sheets",
    )

    class Meta:
        db_table = "pages_sheet"
        verbose_name = "Sheet"
        verbose_name_plural = "Sheets"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class Tab(TimeStampedModel):
    """Individual tab within a sheet."""

    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="tabs")
    name = models.CharField(max_length=255)
    position = models.PositiveIntegerField(default=0)
    is_locked = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Tab"
        verbose_name_plural = "Tabs"
        ordering = ["sheet", "position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["sheet", "name"], name="sheets_tab_sheet_name_uniq"),
            models.UniqueConstraint(fields=["sheet", "position"], name="sheets_tab_sheet_pos_uniq"),
        ]
        indexes = [
            models.Index(fields=["sheet", "position"], name="sheets_tab_sheet_pos_idx"),
        ]

    def __str__(self):
        return f"{self.sheet} / {self.name}"


class Column(TimeStampedModel):
    """Column definition for a tab."""

    tab = models.ForeignKey(Tab, on_delete=models.CASCADE, related_name="columns")
    name = models.CharField(max_length=255)
    key = models.CharField(max_length=100)
    column_type = models.CharField(max_length=50, default="text")
    position = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Column"
        verbose_name_plural = "Columns"
        ordering = ["tab", "position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["tab", "key"], name="sheets_column_tab_key_uniq"),
            models.UniqueConstraint(fields=["tab", "position"], name="sheets_column_tab_pos_uniq"),
        ]
        indexes = [
            models.Index(fields=["tab", "position"], name="sheets_column_tab_pos_idx"),
        ]

    def __str__(self):
        return f"{self.tab} / {self.name}"


class Row(TimeStampedModel):
    """Row of data within a tab."""

    tab = models.ForeignKey(Tab, on_delete=models.CASCADE, related_name="rows")
    position = models.PositiveIntegerField(default=0)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Row"
        verbose_name_plural = "Rows"
        ordering = ["tab", "position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["tab", "position"], name="sheets_row_tab_pos_uniq"),
        ]
        indexes = [
            models.Index(fields=["tab", "position"], name="sheets_row_tab_pos_idx"),
        ]

    def __str__(self):
        return f"{self.tab} / row {self.position}"


class Cell(TimeStampedModel):
    """Cell value mapped to a row/column pair."""

    row = models.ForeignKey(Row, on_delete=models.CASCADE, related_name="cells")
    column = models.ForeignKey(Column, on_delete=models.CASCADE, related_name="cells")
    value = models.JSONField(blank=True, null=True)

    class Meta:
        verbose_name = "Cell"
        verbose_name_plural = "Cells"
        constraints = [
            models.UniqueConstraint(fields=["row", "column"], name="sheets_cell_row_col_uniq"),
        ]
        indexes = [
            models.Index(fields=["row"], name="sheets_cell_row_idx"),
            models.Index(fields=["column"], name="sheets_cell_col_idx"),
        ]

    def __str__(self):
        return f"{self.column}: {self.value}"


class SheetMember(TimeStampedModel):
    """Relationship between members and sheets."""

    ROLE_OWNER = "owner"
    ROLE_EDITOR = "editor"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = (
        (ROLE_OWNER, "Owner"),
        (ROLE_EDITOR, "Editor"),
        (ROLE_VIEWER, "Viewer"),
    )

    sheet = models.ForeignKey(Sheet, on_delete=models.CASCADE, related_name="memberships")
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sheet_memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Sheet Member"
        verbose_name_plural = "Sheet Members"
        ordering = ["sheet", "member"]
        constraints = [
            models.UniqueConstraint(fields=["sheet", "member"], name="sheets_sheetmember_sheet_member_uniq"),
        ]
        indexes = [
            models.Index(fields=["sheet"], name="sheets_sheetmember_sheet_idx"),
            models.Index(fields=["member"], name="sheets_sheetmember_member_idx"),
        ]

    def __str__(self):
        return f"{self.member} in {self.sheet} as {self.role}"
