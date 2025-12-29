from django import forms
from django.contrib import admin
from ..models import PageComponent


class PageComponentForm(forms.ModelForm):
    class Meta:
        model = PageComponent
        fields = "__all__"
        widgets = {
            "html_content": forms.Textarea(attrs={"rows": 12, "class": "vLargeTextField"}),
            "css_code": forms.Textarea(attrs={"rows": 6, "class": "vLargeTextField"}),
        }


@admin.register(PageComponent)
class PageComponentAdmin(admin.ModelAdmin):
    form = PageComponentForm
    list_display = ("component_type", "order", "parent_display", "css_file", "created_at", "updated_at")
    list_filter = ("component_type",)
    search_fields = ("html_content", "css_code")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("component_type", "order", "id")
    fieldsets = (
        (None, {
            "fields": ("component_type", "order", "page", "home_page")
        }),
        ("Content", {
            "fields": ("html_content", "config"),
            "classes": ("wide",),
        }),
        ("Styling", {
            "fields": ("css_file", "css_code"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def parent_display(self, obj):
        """Show parent page/home page for quick identification."""
        if obj.page:
            return f"Page: {obj.page.slug}"
        if obj.home_page:
            return f"Home: {obj.home_page.name}"
        return "Unassigned"

    parent_display.short_description = "Parent"

