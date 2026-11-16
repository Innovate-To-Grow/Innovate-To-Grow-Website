from django.core.exceptions import PermissionDenied

from apps.cms.admin.cms.page_admin.editor import (
    assets_list_response,
    assets_upload_response,
    build_editor_context,
    preview_store_response,
    route_conflict_response,
)
from apps.cms.admin.cms.page_admin.import_export import export_pages_response, render_json_import
from apps.cms.models import CMSPage


class CMSPageEditorViewsMixin:
    """CMSPageAdmin's own admin URLs (preview, route check, asset picker, import/export) and the views that
    hand the block editor its context."""

    def get_urls(self):
        from django.urls import path

        custom_urls = [
            path("preview/", self.admin_site.admin_view(self.preview_store_view), name="cms_cmspage_preview"),
            path(
                "route-conflict/",
                self.admin_site.admin_view(self.route_conflict_view),
                name="cms_cmspage_route_conflict",
            ),
            # Staff CMS editors are trusted to list/upload reusable picker assets;
            # admin_site.admin_view is the intentional access boundary here.
            path("assets/", self.admin_site.admin_view(self.assets_list_view), name="cms_cmspage_assets"),
            path(
                "assets/upload/",
                self.admin_site.admin_view(self.assets_upload_view),
                name="cms_cmspage_asset_upload",
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

    def preview_store_view(self, request):
        # ``admin_view`` only enforces is_staff, so re-check per-app access here:
        # storing a preview mutates server-side state, so require change access.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to preview CMS pages.")
        return preview_store_response(request)

    def route_conflict_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to access CMS pages.")
        return route_conflict_response(request)

    def assets_list_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to access CMS assets.")
        return assets_list_response(request)

    def assets_upload_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to upload CMS assets.")
        return assets_upload_response(request)

    def export_all_view(self, request):
        # CMS page content export; ``admin_view`` only checks is_staff, so re-check
        # per-app access before reading/exporting every page.
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to export CMS pages.")
        queryset = CMSPage.objects.prefetch_related("blocks").all()
        status_filter = request.GET.get("status")
        if status_filter in ("draft", "published", "archived"):
            queryset = queryset.filter(status=status_filter)
        return export_pages_response(queryset)

    def import_view(self, request):
        # Importing pages creates/updates records; require per-app change access
        # because ``admin_view`` only enforces is_staff.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to import CMS pages.")
        return render_json_import(
            self,
            request,
            title="Import CMS Pages",
            template_name="admin/cms/cmspage/import_form.html",
            require_upload=True,
            validate_required=True,
        )
