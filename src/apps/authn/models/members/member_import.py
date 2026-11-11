"""Staged member imports: an uploaded sheet's rows, how each one resolved, and what the admin chose for it.

Members → Import parses and analyses an upload into a ``MemberImportBatch`` with one ``MemberImportRow`` per sheet row.
Nothing touches member data until the batch is applied, in one transaction
(``services/members/import_/review/apply.py``). A batch keeps the parsed values, never the file itself.

Each row stores the records its analysis read (``candidates``) and a SHA-256 of them (``fingerprint``). The apply
re-reads and re-hashes them, so a member or contact that changed after the review sends the row back to review
instead of applying a plan nobody saw.

Retention (``settings.MEMBER_IMPORT``): a batch that was not applied is deleted ``batch_lifetime_hours`` after the
upload; an applied one loses its sheet values and snapshots after ``values_retention_days`` and is deleted after
``rows_retention_days``. The admin's history (LogEntry) of every member change stays.
"""

from django.db import models

from apps.core.models import ProjectControlModel


class MemberImportBatch(ProjectControlModel):
    """One upload of a member sheet, from review to its result."""

    class Status(models.TextChoices):
        REVIEW = "review", "In review"
        APPLIED = "applied", "Applied"
        DISCARDED = "discarded", "Discarded"
        EXPIRED = "expired", "Expired"

    class Mode(models.TextChoices):
        UPDATE_EXISTING = "update_existing", "Update them"
        SKIP_EXISTING = "skip_existing", "Skip them"

    created_by = models.ForeignKey(
        "authn.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Uploaded by"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REVIEW, db_index=True)
    mode = models.CharField(
        max_length=16,
        choices=Mode.choices,
        default=Mode.UPDATE_EXISTING,
        help_text="What a row that matches an existing member does unless the admin chooses otherwise.",
        verbose_name="Rows that match an existing member",
    )
    file_name = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64, db_index=True, verbose_name="File SHA-256")
    file_size = models.PositiveIntegerField(default=0, help_text="Bytes.")
    sheet_name = models.CharField(max_length=255, blank=True, help_text="The worksheet that was read.")
    row_count = models.PositiveIntegerField(default=0, help_text="Data rows read (blank rows are not counted).")
    columns = models.JSONField(default=dict, blank=True, help_text="Recognised and ignored headers.")
    file_warnings = models.JSONField(default=list, blank=True, help_text="Checks about the file as a whole.")
    # ``make_password`` of the upload's Default Password, for the members the import creates. Cleared when the batch
    # is applied, discarded or expires.
    default_password_hash = models.CharField(max_length=128, blank=True)
    choices_version = models.PositiveIntegerField(
        default=0, help_text="Raised by every saved change of choices; the confirm form must carry the current one."
    )
    expires_at = models.DateTimeField(db_index=True, help_text="An unapplied batch is deleted after this.")
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        "authn.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="Applied by"
    )
    summary = models.JSONField(default=dict, blank=True, help_text="Counts per outcome and per risky change.")
    last_error = models.TextField(blank=True, help_text="Why the last attempt to apply was refused.")
    activity = models.JSONField(default=list, blank=True, help_text="Uploads, saves, bulk choices and applies.")
    values_purged_at = models.DateTimeField(
        null=True, blank=True, help_text="When the sheet values and snapshots of this applied batch were blanked."
    )

    class Meta:
        verbose_name = "Member import"
        verbose_name_plural = "Member imports"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["status", "applied_at"]),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.get_status_display()}, {self.created_at:%Y-%m-%d %H:%M})"

    @property
    def short_id(self) -> str:
        return str(self.pk)[:8]


class MemberImportRow(ProjectControlModel):
    """One sheet row of a batch: its values, how it resolved, the admin's choice and, once applied, the outcome."""

    class Status(models.TextChoices):
        READY_CREATE = "ready_create", "Ready to create"
        READY_UPDATE = "ready_update", "Ready to update"
        NO_CHANGE = "no_change", "No change"
        NEEDS_DECISION = "needs_decision", "Needs a decision"
        INVALID = "invalid", "Cannot import"

    class Outcome(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        NO_CHANGE = "no_change", "No change"
        SKIPPED = "skipped", "Skipped by choice"
        NOT_IMPORTED = "not_imported", "Not imported"

    batch = models.ForeignKey(MemberImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField(help_text="The spreadsheet row (the header is row 1).")
    values = models.JSONField(default=dict, blank=True, help_text="The parsed cells and the text as typed.")
    status = models.CharField(max_length=16, choices=Status.choices)
    conflict = models.CharField(max_length=32, blank=True, help_text="The conflict that needs a decision, if any.")
    analysis = models.JSONField(default=dict, blank=True, help_text="Why, the choices offered and the default.")
    candidates = models.JSONField(default=dict, blank=True, help_text="The members and contacts the analysis read.")
    risky = models.JSONField(default=dict, blank=True, help_text="Opt-in risky changes, per member.")
    warnings = models.JSONField(default=list, blank=True)
    choice = models.CharField(max_length=64, blank=True)
    ticks = models.JSONField(default=list, blank=True, help_text="The risky changes ticked.")
    target_member = models.ForeignKey(
        "authn.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    chosen_by = models.ForeignKey("authn.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    chosen_at = models.DateTimeField(null=True, blank=True)
    fingerprint = models.CharField(max_length=64, blank=True, help_text="SHA-256 of the records the analysis read.")
    changed_since_review = models.BooleanField(
        default=False, help_text="A record this row read changed after the review, so its choice was reset."
    )
    outcome = models.CharField(max_length=16, choices=Outcome.choices, blank=True)
    outcome_detail = models.TextField(blank=True)
    result_member = models.ForeignKey(
        "authn.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "Member import row"
        verbose_name_plural = "Member import rows"
        ordering = ["row_number"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "row_number"], name="member_import_row_number_unique"),
        ]
        indexes = [
            models.Index(fields=["batch", "status"]),
            models.Index(fields=["batch", "conflict"]),
        ]

    def __str__(self):
        return f"Row {self.row_number}"
