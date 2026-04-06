import os

from django import forms
from django.contrib import admin
from django.utils.html import format_html

from cms.models import CMSAsset
from core.admin import BaseModelAdmin

_IMAGE_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"}


class CMSAssetAdminForm(forms.ModelForm):
    class Meta:
        model = CMSAsset
        fields = "__all__"
        widgets = {
            "file": forms.ClearableFileInput(
                attrs={"accept": ".svg,.png,.jpg,.jpeg,.webp,.gif"}
            ),
        }


@admin.register(CMSAsset)
class CMSAssetAdmin(BaseModelAdmin):
    form = CMSAssetAdminForm
    list_display = ("name", "file_preview", "public_url_link", "updated_at")
    search_fields = ("name", "file")
    readonly_fields = ("public_url_link", "file_preview", "created_at", "updated_at")
    fieldsets = (
        (
            "Asset",
            {
                "fields": ("name", "file", "public_url_link", "file_preview"),
                "description": "Upload sponsor logos here, then paste the public URL into a sponsor block's logo URL field.",
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Public URL")
    def public_url_link(self, obj):
        if not obj.file:
            return "-"
        return format_html('<a href="{0}" target="_blank" rel="noopener noreferrer">{0}</a>', obj.public_url)

    @admin.display(description="Preview")
    def file_preview(self, obj):
        if not obj.file:
            return "-"
        _, ext = os.path.splitext(obj.file.name)
        if ext.lower() in _IMAGE_EXTENSIONS:
            return format_html(
                '<a href="{0}" target="_blank" rel="noopener noreferrer">'
                '<img src="{0}" alt="{1}" style="max-height: 64px; max-width: 140px; object-fit: contain;" />'
                "</a>",
                obj.public_url,
                obj.name,
            )
        return format_html('<a href="{0}" target="_blank" rel="noopener noreferrer">Open file</a>', obj.public_url)
