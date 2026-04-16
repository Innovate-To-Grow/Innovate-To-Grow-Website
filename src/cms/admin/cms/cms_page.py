import logging

from django import forms
from django.contrib import admin, messages

from cms.admin.cms.page_admin.editor import (
    build_editor_context,
    preview_store_response,
    route_conflict_response,
    save_blocks_from_json,
)
from cms.admin.cms.page_admin.import_export import export_pages_response, render_json_import
from cms.models import CMSPage
from cms.models.content.cms.cms_page import validate_cms_route
from core.admin import BaseModelAdmin

logger = logging.getLogger(__name__)


class CMSPageAdminForm(forms.ModelForm):
    def clean_route(self):
        route = validate_cms_route(self.cleaned_data.get("route"))
        conflict = CMSPage.objects.filter(route=route).exclude(pk=self.instance.pk).first()
        if conflict:
            raise forms.ValidationError(f'Route "{route}" is already used by "{conflict.title}".')
        return route

    class Meta:
        model = CMSPage
        fields = "__all__"
        widgets = {
            "meta_description": forms.TextInput(
                attrs={
                    "class": (
                        "border border-base-200 bg-white font-medium min-w-20 "
                        "placeholder-base-400 rounded-default shadow-xs text-font-default-light text-sm "
                        "focus:outline-2 focus:-outline-offset-2 focus:outline-primary-600 "
                        "h-[38px] w-full max-w-2xl block"
                    )
                }
            ),
            "route": forms.TextInput(
                attrs={"data-role": "cms-route-source", "autocomplete": "off", "spellcheck": "false"}
            ),
        }


@admin.register(CMSPage)
class CMSPageAdmin(BaseModelAdmin):
    form = CMSPageAdminForm
    change_form_template = "admin/cms/cmspage/change_form.html"
    list_display = ("title", "route", "status", "block_count", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "slug", "route")
    readonly_fields = ("created_at", "updated_at", "published_at")
    inlines = []
    actions = ["export_pages"]
    fieldsets = (
        (
            "Page Info",
            {"fields": ("slug", "route", "title", "meta_description", "page_css_class", "status", "sort_order")},
        ),
        (
            "Page CSS",
            {
                "fields": ("page_css",),
                "classes": ("collapse",),
                "description": "Custom CSS injected when this page is loaded. Scoped to the page wrapper.",
            },
        ),
        ("Timestamps", {"fields": ("published_at", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def block_count(self, obj):
        return obj.blocks.count()

    block_count.short_description = "Blocks"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.status == "published":
            readonly.append("slug")
        return readonly

    def get_urls(self):
        from django.urls import path

        custom_urls = [
            path("preview/", self.admin_site.admin_view(self.preview_store_view), name="cms_cmspage_preview"),
            path(
                "route-conflict/",
                self.admin_site.admin_view(self.route_conflict_view),
                name="cms_cmspage_route_conflict",
            ),
            path("import/", self.admin_site.admin_view(self.import_view), name="cms_cmspage_import"),
            path("export/", self.admin_site.admin_view(self.export_all_view), name="cms_cmspage_export"),
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {**(extra_context or {}), "show_import_buttons": True})

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra = {
            **(extra_context or {}),
            **build_editor_context(self.get_object(request, object_id) if object_id else None),
        }
        return super().change_view(request, object_id, form_url, extra)

    def add_view(self, request, form_url="", extra_context=None):
        return super().add_view(request, form_url, {**(extra_context or {}), **build_editor_context()})

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        save_blocks_from_json(request, form.instance, messages)

    def preview_store_view(self, request):
        return preview_store_response(request)

    def route_conflict_view(self, request):
        return route_conflict_response(request)

    @admin.action(description="Export selected pages as JSON")
    def export_pages(self, request, queryset):
        return export_pages_response(queryset)

    def export_all_view(self, request):
        queryset = CMSPage.objects.prefetch_related("blocks").all()
        status_filter = request.GET.get("status")
        if status_filter in ("draft", "published", "archived"):
            queryset = queryset.filter(status=status_filter)
        return export_pages_response(queryset)

    def import_view(self, request):
        return render_json_import(
            self,
            request,
            title="Import CMS Pages",
            template_name="admin/cms/cmspage/import_form.html",
            require_upload=True,
            validate_required=True,
        )
