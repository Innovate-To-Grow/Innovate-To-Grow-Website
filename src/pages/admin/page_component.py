from django import forms
from django.contrib import admin

from ..models import PageComponent


class PageComponentForm(forms.ModelForm):
    """Form for PageComponent with hidden code fields (managed by JS editor)."""

    class Meta:
        model = PageComponent
        fields = "__all__"
        widgets = {
            # These textareas are hidden and synced by the CodeMirror editor
            "html_content": forms.Textarea(attrs={"rows": 12, "class": "vLargeTextField"}),
            "css_code": forms.Textarea(attrs={"rows": 8, "class": "vLargeTextField"}),
            "js_code": forms.Textarea(attrs={"rows": 10, "class": "vLargeTextField"}),
        }


@admin.register(PageComponent)
class PageComponentAdmin(admin.ModelAdmin):
    """
    Admin for PageComponent with integrated code editor.

    The HTML/CSS/JS fields are edited via a CodeMirror-based editor
    with live preview. The textarea fields are hidden but still synced.
    """

    form = PageComponentForm
    change_form_template = "admin/pages/pagecomponent/change_form.html"
    list_display = ("component_type", "order", "parent_display", "created_at", "updated_at")
    list_filter = ("component_type",)
    search_fields = ("html_content", "css_code", "js_code")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("component_type", "order", "id")

    fieldsets = (
        (None, {
            "fields": ("html_content", "css_code", "js_code"),
            "classes": ("wide", "hidden-fieldset"),
        }),
        ("Component Settings", {
            "fields": ("component_type", "order", "page", "home_page"),
            "classes": ("collapse",),
        }),
        ("Additional Settings", {
            "fields": ("config", "css_file"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
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
