from django import forms
from django.contrib import admin
from django.core.cache import cache

from cms.admin.layout.import_export import export_stylesheets_response, render_stylesheet_import
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
    change_list_template = "admin/cms/stylesheet/change_list.html"
    list_display = ("display_name", "name", "is_active", "sort_order")
    list_filter = ("is_active",)
    list_editable = ("is_active", "sort_order")
    search_fields = ("name", "display_name")
    ordering = ("sort_order", "name")

    fieldsets = (
        (None, {"fields": ("name", "display_name", "description", "is_active", "sort_order")}),
        ("CSS", {"fields": ("css",)}),
    )

    def get_urls(self):
        from django.urls import path

        custom_urls = [
            path("import/", self.admin_site.admin_view(self.import_view), name="cms_stylesheet_import"),
            path("export/", self.admin_site.admin_view(self.export_all_view), name="cms_stylesheet_export"),
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {**(extra_context or {}), "show_import_buttons": True})

    def export_all_view(self, request):
        queryset = self.get_queryset(request)
        return export_stylesheets_response(queryset)

    def import_view(self, request):
        return render_stylesheet_import(
            self,
            request,
            title="Import Style Sheets",
            template_name="admin/cms/stylesheet/import_form.html",
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        cache.delete("layout:data")
