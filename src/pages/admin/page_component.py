from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from ..models import ComponentDataSource, PageComponent, PageComponentAsset, PageComponentImage


class PageComponentForm(forms.ModelForm):
    """Form for PageComponent with code editor fields."""

    class Meta:
        model = PageComponent
        fields = "__all__"
        widgets = {
            "html_content": forms.Textarea(attrs={"rows": 12, "class": "vLargeTextField"}),
            "css_code": forms.Textarea(attrs={"rows": 8, "class": "vLargeTextField"}),
            "js_code": forms.Textarea(attrs={"rows": 10, "class": "vLargeTextField"}),
        }


class PageComponentImageInline(TabularInline):
    model = PageComponentImage
    extra = 1
    fields = ("order", "image", "alt", "caption", "link")
    ordering = ("order",)


class PageComponentAssetInline(TabularInline):
    model = PageComponentAsset
    extra = 1
    fields = ("order", "file", "asset_type", "title", "caption", "link")
    ordering = ("order",)


@admin.register(ComponentDataSource)
class ComponentDataSourceAdmin(ModelAdmin):
    list_display = ("source_name", "request_method", "source_url", "auth_mode", "is_enabled")
    list_filter = ("request_method", "auth_mode", "is_enabled")
    search_fields = ("source_name", "source_url")
    ordering = ("source_name",)


@admin.register(PageComponent)
class PageComponentAdmin(ModelAdmin):
    """
    Admin for PageComponent with integrated code editor.
    """

    form = PageComponentForm
    change_form_template = "admin/pages/pagecomponent/change_form.html"
    list_display = ("name", "component_type", "order", "parent_display", "is_enabled", "updated_at")
    list_filter = ("component_type", "is_enabled", "page", "home_page")
    search_fields = ("name", "html_content", "css_code", "js_code")
    ordering = ("order", "name")
    inlines = [PageComponentAssetInline, PageComponentImageInline]

    fieldsets = (
        (None, {"fields": ("name", "component_type", "page", "home_page", "order", "is_enabled")}),
        ("Content", {"fields": ("html_content", "css_code", "js_code", "config")}),
        ("Images", {"fields": ("image", "image_alt", "background_image"), "classes": ("collapse",)}),
        ("Data Source", {"fields": ("data_source", "data_params"), "classes": ("collapse",)}),
    )

    def parent_display(self, obj):
        """Show parent page/home page for quick identification."""
        if obj.page:
            return f"Page: {obj.page.slug}"
        if obj.home_page:
            return f"Home: {obj.home_page.name}"
        return "Unassigned"

    parent_display.short_description = "Parent"


@admin.register(PageComponentImage)
class PageComponentImageAdmin(ModelAdmin):
    list_display = ("image_uuid", "component", "order", "alt")
    list_filter = ("component",)
    search_fields = ("alt", "caption")
    ordering = ("component", "order")
