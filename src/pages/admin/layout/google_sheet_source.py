import json

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from django.utils import timezone
from unfold.admin import ModelAdmin

from ...models import GoogleSheetSource


@admin.register(GoogleSheetSource)
class GoogleSheetSourceAdmin(ModelAdmin):
    list_display = ("slug", "title", "sheet_type", "is_active", "created_at")
    list_filter = ("sheet_type", "is_active")
    search_fields = ("slug", "title")
    readonly_fields = ("created_at", "updated_at")
    actions = ["export_sources"]

    fieldsets = (
        (None, {"fields": ("slug", "title", "sheet_type", "is_active")}),
        ("Spreadsheet", {"fields": ("spreadsheet_id", "range_a1")}),
        ("Tracks", {"fields": ("tracks_spreadsheet_id", "tracks_sheet_name"), "classes": ("collapse",)}),
        ("Filtering & Cache", {"fields": ("semester_filter", "cache_ttl_seconds")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def get_urls(self):
        custom_urls = [
            path("import/", self.admin_site.admin_view(self.import_view), name="pages_googlesheetsource_import"),
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_import_buttons"] = True
        return super().changelist_view(request, extra_context)

    def _serialize_source(self, source):
        return {
            "slug": source.slug,
            "title": source.title,
            "sheet_type": source.sheet_type,
            "spreadsheet_id": source.spreadsheet_id,
            "range_a1": source.range_a1,
            "tracks_spreadsheet_id": source.tracks_spreadsheet_id,
            "tracks_sheet_name": source.tracks_sheet_name,
            "semester_filter": source.semester_filter,
            "cache_ttl_seconds": source.cache_ttl_seconds,
            "is_active": source.is_active,
        }

    def _build_source_from_data(self, source, source_data):
        source.slug = source_data.get("slug", "")
        source.title = source_data.get("title", "")
        source.sheet_type = source_data.get("sheet_type", "")
        source.spreadsheet_id = source_data.get("spreadsheet_id", "")
        source.range_a1 = source_data.get("range_a1", "")
        source.tracks_spreadsheet_id = source_data.get("tracks_spreadsheet_id", "")
        source.tracks_sheet_name = source_data.get("tracks_sheet_name", "")
        source.semester_filter = source_data.get("semester_filter", "")
        source.cache_ttl_seconds = source_data.get("cache_ttl_seconds", 300)
        source.is_active = source_data.get("is_active", True)
        return source

    @admin.action(description="Export selected sheet sources as JSON")
    def export_sources(self, request, queryset):
        sources_data = [self._serialize_source(source) for source in queryset.order_by("slug")]
        content = json.dumps(
            {
                "version": 1,
                "exported_at": timezone.now().isoformat(),
                "sources": sources_data,
            },
            indent=2,
            ensure_ascii=False,
        )
        response = HttpResponse(content, content_type="application/json")
        filename = f"sheet_sources_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def import_view(self, request):
        context = {
            **self.admin_site.each_context(request),
            "title": "Import Sheet Sources",
            "opts": self.model._meta,
        }

        if request.method != "POST":
            return render(request, "admin/pages/googlesheetsource/import_form.html", context)

        json_file = request.FILES.get("json_file")
        if not json_file:
            messages.error(request, "Please select a JSON file to import.")
            return render(request, "admin/pages/googlesheetsource/import_form.html", context)

        try:
            raw = json_file.read().decode("utf-8")
            bundle = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            messages.error(request, f"Invalid JSON file: {exc}")
            return render(request, "admin/pages/googlesheetsource/import_form.html", context)

        if not isinstance(bundle, dict) or "sources" not in bundle:
            messages.error(request, "Invalid format: expected a JSON object with a 'sources' key.")
            return render(request, "admin/pages/googlesheetsource/import_form.html", context)

        sources_data = bundle["sources"]
        if not isinstance(sources_data, list):
            messages.error(request, "Invalid format: 'sources' must be a list.")
            return render(request, "admin/pages/googlesheetsource/import_form.html", context)

        action = request.POST.get("action", "dry_run")
        results = []

        for source_data in sources_data:
            if not isinstance(source_data, dict):
                results.append(
                    {
                        "slug": "",
                        "title": "",
                        "sheet_type": "",
                        "action": "",
                        "errors": ["Each source entry must be a JSON object."],
                    }
                )
                continue

            slug = source_data.get("slug", "")
            title = source_data.get("title", "")
            sheet_type = source_data.get("sheet_type", "")
            result = {
                "slug": slug,
                "title": title,
                "sheet_type": sheet_type,
                "errors": [],
                "action": "",
            }

            existing = GoogleSheetSource.objects.filter(slug=slug).first() if slug else None
            result["action"] = "update" if existing else "create"

            candidate = self._build_source_from_data(existing or GoogleSheetSource(), source_data)
            try:
                candidate.full_clean()
            except ValidationError as exc:
                for field_errors in exc.message_dict.values():
                    result["errors"].extend(field_errors)

            if result["errors"]:
                results.append(result)
                continue

            if action == "execute":
                candidate.save()
                result["success"] = True

            results.append(result)

        if action == "execute":
            success_count = sum(1 for result in results if result.get("success"))
            error_count = sum(1 for result in results if result.get("errors"))
            if success_count:
                messages.success(request, f"Successfully imported {success_count} sheet source(s).")
            if error_count:
                messages.warning(request, f"{error_count} sheet source(s) had errors.")

        context["results"] = results
        context["is_dry_run"] = action != "execute"
        context["has_results"] = True
        return render(request, "admin/pages/googlesheetsource/import_form.html", context)
