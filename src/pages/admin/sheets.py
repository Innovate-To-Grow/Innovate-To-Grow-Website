from django.contrib import admin

from sheets.models import Sheet


@admin.register(Sheet)
class SheetAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "created_at", "updated_at")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "description",
                )
            },
        ),
        (
            "Data",
            {
                "fields": ("columns", "data"),
                "description": "Column definitions and row data stored as JSON.",
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
