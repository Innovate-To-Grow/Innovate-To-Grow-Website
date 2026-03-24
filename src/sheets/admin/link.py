import json
import logging

from django.contrib import admin, messages
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from unfold.admin import ModelAdmin

from sheets.models import SheetLink

logger = logging.getLogger(__name__)

# Only show models from these apps in the content_type dropdown
ALLOWED_APP_LABELS = {"authn", "event", "news", "pages", "projects"}


@admin.register(SheetLink)
class SheetLinkAdmin(ModelAdmin):
    change_form_template = "admin/sheets/sheetlink/change_form.html"
    list_display = ("name", "content_type", "spreadsheet_id_short", "sync_direction", "is_active", "last_sync_status")
    list_filter = ("sync_direction", "is_active", "content_type")
    search_fields = ("name", "spreadsheet_id")
    readonly_fields = ("id", "created_at", "updated_at")
    actions = ["pull_selected", "push_selected"]

    fieldsets = (
        (None, {"fields": ("name", "account", "is_active", "sync_direction")}),
        (
            "Google Sheet",
            {
                "fields": ("spreadsheet_id", "sheet_name", "range_a1"),
            },
        ),
        (
            "Target Model",
            {
                "fields": ("content_type",),
            },
        ),
        (
            "Column Mapping",
            {
                "fields": ("column_mapping", "fk_config"),
                "description": (
                    "Map sheet headers to model fields. Use Django __ syntax for FKs: "
                    '{"Year": "semester__year"}. Use "__skip__" to ignore a column.'
                ),
            },
        ),
        (
            "Upsert Configuration",
            {
                "fields": ("lookup_fields", "row_transform_hook"),
                "description": "Fields forming the unique key for upserts, and optional transform hook.",
            },
        ),
        (
            "Metadata",
            {
                "fields": ("id", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "content_type":
            kwargs["queryset"] = ContentType.objects.filter(app_label__in=ALLOWED_APP_LABELS).order_by(
                "app_label", "model"
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="Sheet ID")
    def spreadsheet_id_short(self, obj):
        sid = obj.spreadsheet_id
        if len(sid) > 20:
            return f"{sid[:10]}...{sid[-6:]}"
        return sid

    @admin.display(description="Last Sync")
    def last_sync_status(self, obj):
        last_log = obj.sync_logs.order_by("-started_at").first()
        if not last_log:
            return "—"
        return (
            f"{last_log.get_direction_display()} {last_log.get_status_display()} ({last_log.started_at:%Y-%m-%d %H:%M})"
        )

    # ------------------------------------------------------------------
    # Column mapping visual editor context
    # ------------------------------------------------------------------

    def _get_editor_context(self, obj=None):
        # Build URL with a placeholder; can't use reverse() with non-int placeholder
        base_url = reverse("admin:sheets_sheetlink_model_fields", args=[0])
        model_fields_url = base_url.replace("/0/", "/__CT_ID__/")
        return {
            "initial_mapping_json": json.dumps(obj.column_mapping if obj else {}),
            "model_fields_url": model_fields_url,
        }

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id) if object_id else None
        extra_context.update(self._get_editor_context(obj))
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context.update(self._get_editor_context())
        return super().add_view(request, form_url, extra_context)

    # ------------------------------------------------------------------
    # AJAX endpoint: model fields for a content type
    # ------------------------------------------------------------------

    def model_fields_view(self, request, content_type_id):
        """Return JSON list of model fields for the given content_type."""
        ct = ContentType.objects.filter(id=content_type_id, app_label__in=ALLOWED_APP_LABELS).first()
        if not ct:
            return JsonResponse({"fields": []})

        model_class = ct.model_class()
        if not model_class:
            return JsonResponse({"fields": []})

        fields = []
        for f in model_class._meta.get_fields():
            if f.is_relation and hasattr(f, "related_model") and f.related_model and f.many_to_one:
                # FK field — expand to show related model's concrete fields
                related_model = f.related_model
                for rf in related_model._meta.get_fields():
                    if not rf.is_relation and hasattr(rf, "column"):
                        fields.append(
                            {
                                "value": f"{f.name}__{rf.name}",
                                "label": f"{f.name} \u2192 {rf.name} ({rf.get_internal_type()})",
                                "group": f"FK: {f.name}",
                            }
                        )
            elif not f.is_relation and hasattr(f, "column"):
                # Skip auto primary key
                if f.primary_key and f.name == "id":
                    continue
                fields.append(
                    {
                        "value": f.name,
                        "label": f"{f.name} ({f.get_internal_type()})",
                        "group": "Direct fields",
                    }
                )

        return JsonResponse({"fields": fields})

    # ------------------------------------------------------------------
    # Custom URLs for pull/push
    # ------------------------------------------------------------------

    def get_urls(self):
        custom_urls = [
            path(
                "model-fields/<int:content_type_id>/",
                self.admin_site.admin_view(self.model_fields_view),
                name="sheets_sheetlink_model_fields",
            ),
            path(
                "<path:object_id>/pull/",
                self.admin_site.admin_view(self.pull_view),
                name="sheets_sheetlink_pull",
            ),
            path(
                "<path:object_id>/push/",
                self.admin_site.admin_view(self.push_view),
                name="sheets_sheetlink_push",
            ),
        ]
        return custom_urls + super().get_urls()

    def pull_view(self, request, object_id):
        sheet_link = self.get_object(request, object_id)
        if sheet_link is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)

        if request.method == "POST":
            from sheets.services.sync import pull_from_sheet

            sync_log = pull_from_sheet(sheet_link, triggered_by=request.user)
            return render(
                request,
                "admin/sheets/sheetlink/sync_result.html",
                {
                    **self.admin_site.each_context(request),
                    "title": f"Pull Result: {sheet_link.name}",
                    "opts": self.opts,
                    "sync_log": sync_log,
                    "sheet_link": sheet_link,
                },
            )

        return render(
            request,
            "admin/sheets/sheetlink/sync_confirm.html",
            {
                **self.admin_site.each_context(request),
                "title": f"Pull from Sheet: {sheet_link.name}",
                "opts": self.opts,
                "sheet_link": sheet_link,
                "action": "pull",
            },
        )

    def push_view(self, request, object_id):
        sheet_link = self.get_object(request, object_id)
        if sheet_link is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)

        if request.method == "POST":
            from sheets.services.sync import push_to_sheet

            sync_log = push_to_sheet(sheet_link, triggered_by=request.user)
            return render(
                request,
                "admin/sheets/sheetlink/sync_result.html",
                {
                    **self.admin_site.each_context(request),
                    "title": f"Push Result: {sheet_link.name}",
                    "opts": self.opts,
                    "sync_log": sync_log,
                    "sheet_link": sheet_link,
                },
            )

        return render(
            request,
            "admin/sheets/sheetlink/sync_confirm.html",
            {
                **self.admin_site.each_context(request),
                "title": f"Push to Sheet: {sheet_link.name}",
                "opts": self.opts,
                "sheet_link": sheet_link,
                "action": "push",
            },
        )

    # ------------------------------------------------------------------
    # Bulk actions
    # ------------------------------------------------------------------

    @admin.action(description="Pull selected links (Sheet → DB)")
    def pull_selected(self, request, queryset):
        from sheets.services.sync import pull_from_sheet

        success, failed = 0, 0
        for link in queryset.filter(is_active=True):
            log = pull_from_sheet(link, triggered_by=request.user)
            if log.status == "failed":
                failed += 1
            else:
                success += 1

        messages.success(request, f"Pull complete: {success} succeeded, {failed} failed.")

    @admin.action(description="Push selected links (DB → Sheet)")
    def push_selected(self, request, queryset):
        from sheets.services.sync import push_to_sheet

        success, failed = 0, 0
        for link in queryset.filter(is_active=True):
            log = push_to_sheet(link, triggered_by=request.user)
            if log.status == "failed":
                failed += 1
            else:
                success += 1

        messages.success(request, f"Push complete: {success} succeeded, {failed} failed.")
