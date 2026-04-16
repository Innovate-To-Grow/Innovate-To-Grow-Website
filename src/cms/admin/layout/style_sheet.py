from django import forms
from django.contrib import admin
from django.core.cache import cache

from core.admin import BaseModelAdmin

from ...models import StyleSheet


class StyleSheetForm(forms.ModelForm):
    css = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 30, "style": "font-family: monospace; font-size: 13px; width: 100%;"}),
        required=False,
    )

    class Meta:
        model = StyleSheet
        fields = "__all__"


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
