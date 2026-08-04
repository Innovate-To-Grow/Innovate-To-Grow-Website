import logging

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count

from apps.cms.admin.cms.page_admin.editor import (
    assets_list_response,
    assets_upload_response,
    build_editor_context,
    preview_store_response,
    route_conflict_response,
    save_blocks_from_json,
)
from apps.cms.admin.cms.page_admin.import_export import export_pages_response, render_json_import
from apps.cms.models import CMSPage
from apps.cms.services.page_routes import apply_page_route_change
from apps.cms.services.route_redirects import page_route_conflicts
from apps.core.admin import BaseModelAdmin

logger = logging.getLogger(__name__)


class CMSPageAdminForm(forms.ModelForm):
    keep_previous_url_as_redirect = forms.BooleanField(
        required=False,
        label="Keep previous URL as a permanent redirect",
        help_text=(
            "When this published page's route changes, create an active 301 mapping from the old route and "
            "retarget existing inbound mappings to the new route."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["keep_previous_url_as_redirect"].initial = bool(
            self.instance.pk and self.instance.status == "published" and self.instance.route != "/"
        )

    def clean_route(self):
        route, conflicts = page_route_conflicts(
            self.cleaned_data.get("route"),
            exclude_page_id=self.instance.pk,
        )
        if conflicts:
            raise forms.ValidationError(conflicts[0].message)
        return route

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk or not cleaned_data.get("keep_previous_url_as_redirect"):
            return cleaned_data

        old_route = CMSPage.objects.filter(pk=self.instance.pk).values_list("route", flat=True).first()
        route_changed = old_route is not None and old_route != cleaned_data.get("route")
        if route_changed and old_route == "/":
            self.add_error(
                "keep_previous_url_as_redirect",
                "The site root cannot be a redirect source. Uncheck this option to rename the page.",
            )
        if route_changed and cleaned_data.get("status") != "published":
            self.add_error(
                "keep_previous_url_as_redirect",
                "The renamed destination must remain published to create an active redirect.",
            )
        return cleaned_data

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
    actions_no_confirmation = ["export_pages"]
    fieldsets = (
        (
            "Page Info",
            {
                "fields": (
                    "slug",
                    "route",
                    "keep_previous_url_as_redirect",
                    "title",
                    "meta_description",
                    "page_css_class",
                    "status",
                    "sort_order",
                )
            },
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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_block_count=Count("blocks"))

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None:
            return fieldsets

        # A new page has no previous public URL to preserve.
        result = []
        for title, options in fieldsets:
            options = options.copy()
            fields = options.get("fields", ())
            options["fields"] = tuple(field for field in fields if field != "keep_previous_url_as_redirect")
            result.append((title, options))
        return tuple(result)

    @admin.display(description="Blocks", ordering="_block_count")
    def block_count(self, obj):
        return getattr(obj, "_block_count", obj.blocks.count())

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.status == "published":
            readonly.append("slug")
        return readonly

    def has_delete_permission(self, request, obj=None):
        if obj is not None:
            from apps.cms.models import RouteRedirect

            if RouteRedirect.objects.filter(is_active=True, destination_path=obj.route).exists():
                return False
        return super().has_delete_permission(request, obj)

    def get_deleted_objects(self, objs, request):
        deleted_objects, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
        routes = [obj.route for obj in objs]
        if routes:
            from apps.cms.models import RouteRedirect

            protected = [
                *protected,
                *(
                    f'Active route redirect "{source}" points to "{destination}".'
                    for source, destination in RouteRedirect.objects.filter(
                        is_active=True,
                        destination_path__in=routes,
                    ).values_list("source_path", "destination_path")
                ),
            ]
        return deleted_objects, model_count, perms_needed, protected

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

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        save_blocks_from_json(request, form.instance, messages)

    def save_model(self, request, obj, form, change):
        old_route = None
        if change and obj.pk:
            old_route = CMSPage.objects.filter(pk=obj.pk).values_list("route", flat=True).first()

        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if old_route and old_route != obj.route:
                apply_page_route_change(
                    page=obj,
                    old_route=old_route,
                    keep_redirect=bool(form.cleaned_data.get("keep_previous_url_as_redirect")),
                )

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

    @admin.action(description="Export selected pages as JSON")
    def export_pages(self, request, queryset):
        return export_pages_response(queryset)

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
