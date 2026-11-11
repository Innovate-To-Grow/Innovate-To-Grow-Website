"""Members → Member Imports: the read-only history of staged and applied member imports.

Each import links to its own page (Review while in review, the result afterwards). The rows are shown inline with
each row's choice, who made it and when, and the outcome. Nothing here can be changed or exported: the batches hold
personal data until the purge blanks or deletes them (``services/members/import_/review/purge.py``).
"""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import TabularInline

from apps.core.admin import ReadOnlyModelAdmin

from ...models import MemberImportBatch, MemberImportRow


class MemberImportRowInline(TabularInline):
    model = MemberImportRow
    fields = ("row_number", "status", "conflict", "choice", "chosen_by", "chosen_at", "outcome", "result_member")
    readonly_fields = fields
    ordering = ("row_number",)
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MemberImportBatch)
class MemberImportBatchAdmin(ReadOnlyModelAdmin):
    list_display = ("created_at", "file_name", "created_by", "status", "counts", "applied_at", "open_link")
    list_filter = ("status", "mode")
    search_fields = ("file_name", "file_sha256")
    ordering = ("-created_at",)
    fields = (
        "open_link",
        "file_name",
        "file_sha256",
        "file_size",
        "sheet_name",
        "row_count",
        "mode",
        "status",
        "created_by",
        "created_at",
        "expires_at",
        "applied_by",
        "applied_at",
        "counts",
        "last_error",
        "values_purged_at",
    )
    readonly_fields = fields
    inlines = [MemberImportRowInline]

    def get_actions(self, request):
        # No "Export selected data": the rows hold sheet values and member snapshots.
        return {}

    @admin.display(description="Rows")
    def counts(self, obj):
        outcomes = (obj.summary or {}).get("outcomes")
        if not outcomes:
            return f"{obj.row_count} in the sheet"
        order = ("created", "updated", "no_change", "skipped", "not_imported")
        return ", ".join(f"{outcomes.get(key, 0)} {key.replace('_', ' ')}" for key in order)

    @admin.display(description="Page")
    def open_link(self, obj):
        if obj.status == MemberImportBatch.Status.REVIEW:
            return format_html(
                '<a href="{}">Open the review</a>', reverse("admin:authn_member_import_review", args=[obj.pk])
            )
        return format_html(
            '<a href="{}">Open the result</a>', reverse("admin:authn_member_import_result", args=[obj.pk])
        )
