"""
MediaAsset Admin configuration.

Provides a management interface for uploaded media files with
preview, filtering, and search capabilities.
"""

from django.contrib import admin
from django.utils.html import format_html

from ..models import MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    """Admin interface for MediaAsset model."""
    
    list_display = (
        "thumbnail_preview",
        "original_name",
        "content_type",
        "file_size_display",
        "uploaded_by",
        "uploaded_at",
    )
    list_filter = ("content_type", "uploaded_at")
    search_fields = ("original_name", "alt_text", "uuid")
    readonly_fields = (
        "uuid",
        "file_size",
        "uploaded_at",
        "preview_large",
        "file_url_display",
    )
    ordering = ("-uploaded_at",)
    
    fieldsets = (
        (None, {
            "fields": ("file", "original_name", "alt_text"),
        }),
        ("File Info", {
            "fields": ("uuid", "content_type", "file_size", "file_url_display"),
            "classes": ("collapse",),
        }),
        ("Preview", {
            "fields": ("preview_large",),
        }),
        ("Metadata", {
            "fields": ("uploaded_by", "uploaded_at"),
            "classes": ("collapse",),
        }),
    )
    
    def thumbnail_preview(self, obj):
        """Display a small thumbnail in list view."""
        if obj.is_image and obj.file:
            return format_html(
                '<img src="{}" style="max-width: 60px; max-height: 60px; '
                'object-fit: cover; border-radius: 4px;" />',
                obj.url
            )
        return format_html(
            '<span style="color: #666; font-size: 12px;">📄 {}</span>',
            obj.extension.upper() or "FILE"
        )
    thumbnail_preview.short_description = "Preview"
    
    def preview_large(self, obj):
        """Display a larger preview in detail view."""
        if obj.is_image and obj.file:
            return format_html(
                '<img src="{}" style="max-width: 400px; max-height: 300px; '
                'border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);" />',
                obj.url
            )
        return format_html(
            '<div style="padding: 20px; background: #f5f5f5; border-radius: 8px; '
            'text-align: center; color: #666;">'
            '<span style="font-size: 48px;">📄</span><br/>'
            '<span>{}</span></div>',
            obj.original_name
        )
    preview_large.short_description = "Preview"
    
    def file_size_display(self, obj):
        """Display file size in human-readable format."""
        size = obj.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"
    file_size_display.short_description = "Size"
    
    def file_url_display(self, obj):
        """Display the file URL with a copy button."""
        if obj.file:
            return format_html(
                '<code style="background: #f5f5f5; padding: 4px 8px; '
                'border-radius: 4px; font-size: 12px;">{}</code>',
                obj.url
            )
        return "-"
    file_url_display.short_description = "URL"
    
    def save_model(self, request, obj, form, change):
        """Auto-set uploaded_by when creating new assets."""
        if not change and not obj.uploaded_by:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

