from django import forms
from django.contrib import admin
from django.core.cache import cache

from core.admin import BaseModelAdmin

from ...models import StyleSheet


class StyleSheetForm(forms.ModelForm):
    css = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 36,
                "spellcheck": "false",
                "autocapitalize": "off",
                "autocomplete": "off",
                "class": "vLargeTextField code-editor-field",
                "style": (
                    "font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "
                    "'Liberation Mono', 'Courier New', monospace; "
                    "font-size: 14px; line-height: 1.6; width: 100%; min-height: 70vh; "
                    "tab-size: 2; white-space: pre; overflow: auto; resize: vertical;"
                ),
            }
        ),
        required=False,
    )

    class Meta:
        model = StyleSheet
        fields = "__all__"

    class Media:
        css = {"all": ("admin/css/style-sheet-code-editor.css",)}


@admin.register(StyleSheet)
class StyleSheetAdmin(BaseModelAdmin):
    form = StyleSheetForm
    list_display = ("display_name", "name", "is_active", "sort_order")
    list_filter = ("is_active",)
    list_editable = ("is_active", "sort_order")
    search_fields = ("name", "display_name")
    ordering = ("sort_order", "name")

    fieldsets = (
        (None, {"fields": ("name", "display_name", "description", "is_active", "sort_order")}),
        ("CSS", {"fields": ("css",)}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        cache.delete("layout:data")
