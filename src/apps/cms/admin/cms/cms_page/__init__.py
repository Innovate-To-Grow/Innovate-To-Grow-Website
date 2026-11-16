import logging

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count

from apps.cms.admin.cms.page_admin.editor import save_blocks_from_json
from apps.cms.models import CMSPage
from apps.cms.services.routing.page_routes import apply_page_route_change
from apps.core.admin import BaseModelAdmin

from .actions import CMSPageActionsMixin
from .form import CMSPageAdminForm
from .views import CMSPageEditorViewsMixin

logger = logging.getLogger(__name__)


@admin.register(CMSPage)
class CMSPageAdmin(CMSPageEditorViewsMixin, CMSPageActionsMixin, BaseModelAdmin):
    form = CMSPageAdminForm
    change_form_template = "admin/cms/cmspage/change_form.html"
    list_display = ("title", "route", "status", "block_count", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "slug", "route")
    readonly_fields = ("created_at", "updated_at", "published_at")
    inlines = []
    actions = ["duplicate_pages", "export_pages"]
    # Duplicating only adds draft rows, so it is as safe to run unconfirmed as export.
    actions_no_confirmation = ["duplicate_pages", "export_pages"]
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
