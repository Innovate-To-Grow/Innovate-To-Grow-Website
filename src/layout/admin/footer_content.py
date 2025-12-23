from django.contrib import admin

from ..models import FooterContent


@admin.register(FooterContent)
class FooterContentAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    change_form_template = "admin/layout/footercontent/change_form.html"

    fieldsets = (
        (None, {"fields": ("name", "slug", "is_active")}),
        ("Footer Content", {"fields": ("content",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
