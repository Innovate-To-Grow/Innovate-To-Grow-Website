from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from ...models import ComponentDataSource, PageComponent, PageComponentAsset, PageComponentImage, PageComponentPlacement


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


class PlacementInline(TabularInline):
    """Inline showing where this component is placed."""

    model = PageComponentPlacement
    extra = 0
    fields = ("page", "home_page", "order")
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
    list_display = ("name", "component_type", "parent_display", "is_enabled", "updated_at")
    list_filter = ("component_type", "is_enabled")
    search_fields = ("name", "html_content", "css_code", "js_code")
    ordering = ("name",)
    inlines = [PlacementInline, PageComponentAssetInline, PageComponentImageInline]

    fieldsets = (
        (None, {"fields": ("name", "component_type", "is_enabled")}),
        ("Content", {"fields": ("html_content", "css_code", "js_code", "config")}),
        ("Images", {"fields": ("image", "image_alt", "background_image"), "classes": ("collapse",)}),
        ("Google Sheet", {"fields": ("google_sheet", "google_sheet_style"), "classes": ("collapse",)}),
        ("Data Source", {"fields": ("data_source", "data_params"), "classes": ("collapse",)}),
    )

    def parent_display(self, obj):
        """Show parent pages/home pages for quick identification."""
        placements = obj.placements.select_related("page", "home_page")
        parts = []
        for p in placements[:3]:
            if p.page_id:
                parts.append(f"Page: {p.page.slug}")
            if p.home_page_id:
                parts.append(f"Home: {p.home_page.name}")
        return ", ".join(parts) if parts else "Unassigned"

    parent_display.short_description = "Parent"


@admin.register(PageComponentPlacement)
class PageComponentPlacementAdmin(ModelAdmin):
    list_display = ("component", "page", "home_page", "order")
    list_filter = ("page", "home_page")
    ordering = ("order",)
    autocomplete_fields = ["component", "page", "home_page"]


@admin.register(PageComponentImage)
class PageComponentImageAdmin(ModelAdmin):
    list_display = ("image_uuid", "component", "order", "alt")
    list_filter = ("component",)
    search_fields = ("alt", "caption")
    ordering = ("component", "order")
