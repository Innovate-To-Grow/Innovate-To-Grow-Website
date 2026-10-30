from django.db import models

from apps.core.models import ProjectControlModel


class JSONArrayLength(models.Func):
    """The number of elements of a JSON array column (0 for any other JSON value), counted by the database."""

    function = "JSON_ARRAY_LENGTH"
    output_field = models.IntegerField()

    def as_postgresql(self, compiler, connection, **extra_context):
        # JSONField is jsonb on PostgreSQL, whose array length raises on a non-array value.
        return self.as_sql(
            compiler,
            connection,
            template=(
                "CASE WHEN JSONB_TYPEOF(%(expressions)s) = 'array' THEN JSONB_ARRAY_LENGTH(%(expressions)s) ELSE 0 END"
            ),
            **extra_context,
        )


class PastProjectShareQuerySet(models.QuerySet):
    def summaries(self):
        """Shares for a list: their row count comes from the database, and the row and detail payloads (up to a
        couple of MB each) are never loaded."""
        return self.defer("rows", "details_text").annotate(row_count=JSONArrayLength("rows"))


class PastProjectShare(ProjectControlModel):
    name = models.CharField(max_length=200, default="")
    rows = models.JSONField(default=list)
    note = models.TextField(blank=True, default="")
    details_text = models.TextField(blank=True, default="")
    version = models.PositiveBigIntegerField(
        default=1,
        db_default=1,
        editable=False,
        help_text="Monotonic snapshot version used to reject stale whole-document updates.",
    )
    # Deleting an account deletes the curations the member shared: the account page promises that deleting it
    # removes the member's connected data, and an ownerless share could no longer be changed or taken down.
    created_by = models.ForeignKey(
        "authn.Member",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="past_project_shares",
    )

    objects = PastProjectShareQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Project Resource Share"
        verbose_name_plural = "Project Resource Shares"

    def __str__(self):
        return self.name or f"Project Resource Share {self.pk}"
