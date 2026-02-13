import json

from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline

from ..models import Page, PageComponent
from .import_export import deserialize_page, serialize_page
from .page_component import PageComponentForm


class PageComponentInline(StackedInline):
    model = PageComponent
    fk_name = "page"
    extra = 0
    form = PageComponentForm
    fields = (
        "name",
        "component_type",
        "order",
        "is_enabled",
        "html_content",
        "config",
    )
    ordering = ("order", "id")
    show_change_link = True


@admin.register(Page)
class PageAdmin(ModelAdmin):
    inlines = [PageComponentInline]
    change_form_template = "admin/pages/page/change_form.html"
    change_list_template = "admin/pages/page/change_list.html"
    list_display = ("title", "slug", "status_badge", "view_count", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = (
        "status",
        "published_at",
        "published_by",
    )

    fieldsets = (
        (None, {"fields": ("title", "slug", "template_name")}),
        (
            "Publishing",
            {
                "fields": (
                    "status",
                    "published_at",
                    "published_by",
                ),
            },
        ),
        (
            "SEO",
            {
                "fields": ("meta_title", "meta_description"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["action_submit_for_review", "action_publish", "action_unpublish", "action_export_json"]

    def status_badge(self, obj):
        """Display a colored status badge in the list view."""
        colors = {
            "draft": "#6c757d",
            "review": "#f0ad4e",
            "published": "#5cb85c",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{}; color:white; padding:3px 10px; '
            'border-radius:12px; font-size:11px; font-weight:500;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def save_model(self, request, obj, form, change):
        """Save model and auto-create version for edit tracking."""
        super().save_model(request, obj, form, change)
        if change:
            obj.save_version(
                comment=f"Edited via admin by {request.user}",
                user=request.user,
            )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Pass version history and workflow context to the template."""
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj:
            extra_context["versions"] = obj.get_versions()[:20]
            extra_context["current_status"] = obj.status
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def response_change(self, request, obj):
        """Handle custom workflow button clicks from the change form."""

        if "_submit_for_review" in request.POST:
            try:
                obj.submit_for_review(user=request.user)
                self.message_user(
                    request,
                    f'"{obj.title}" has been submitted for review.',
                    messages.SUCCESS,
                )
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_publish" in request.POST:
            try:
                obj.publish(user=request.user)
                self.message_user(
                    request,
                    f'"{obj.title}" has been published.',
                    messages.SUCCESS,
                )
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_unpublish" in request.POST:
            obj.unpublish(user=request.user)
            self.message_user(
                request,
                f'"{obj.title}" has been unpublished.',
                messages.WARNING,
            )
            return HttpResponseRedirect(request.path)

        if "_reject_review" in request.POST:
            try:
                obj.reject_review(user=request.user)
                self.message_user(
                    request,
                    f'"{obj.title}" review rejected, reverted to draft.',
                    messages.WARNING,
                )
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_rollback" in request.POST:
            version_number = request.POST.get("_rollback")
            if version_number:
                try:
                    obj.rollback(int(version_number), user=request.user)
                    self.message_user(
                        request,
                        f'"{obj.title}" rolled back to version {version_number}.',
                        messages.SUCCESS,
                    )
                except ValueError as e:
                    self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        return super().response_change(request, obj)

    # ========================
    # Import / Export
    # ========================

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import/",
                self.admin_site.admin_view(self.import_view),
                name="pages_page_import",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_url"] = reverse("admin:pages_page_import")
        return super().changelist_view(request, extra_context=extra_context)

    def import_view(self, request):
        """Handle JSON import for Pages."""
        context = {**self.admin_site.each_context(request), "title": "Import Page JSON"}

        if request.method == "POST":
            json_file = request.FILES.get("json_file")
            if not json_file:
                context["error"] = "No file uploaded."
                return TemplateResponse(request, "admin/pages/page/import_form.html", context)

            try:
                data = json.load(json_file)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                context["error"] = f"Invalid JSON file: {e}"
                return TemplateResponse(request, "admin/pages/page/import_form.html", context)

            # Support both single page and array of pages
            items = data if isinstance(data, list) else [data]
            all_warnings = []
            imported_count = 0

            for item in items:
                if item.get("export_type") != "page":
                    all_warnings.append(
                        f"Skipped entry with export_type='{item.get('export_type')}' (expected 'page')."
                    )
                    continue
                try:
                    page, warnings = deserialize_page(item, user=request.user)
                    all_warnings.extend(warnings)
                    imported_count += 1
                except Exception as e:
                    all_warnings.append(f"Error importing page: {e}")

            if imported_count:
                self.message_user(
                    request,
                    f"Successfully imported {imported_count} page(s).",
                    messages.SUCCESS,
                )
            if all_warnings:
                context["warnings"] = all_warnings
                return TemplateResponse(request, "admin/pages/page/import_form.html", context)

            return HttpResponseRedirect(reverse("admin:pages_page_changelist"))

        return TemplateResponse(request, "admin/pages/page/import_form.html", context)

    @admin.action(description="Export selected pages as JSON")
    def action_export_json(self, request, queryset):
        pages = list(queryset)
        if len(pages) == 1:
            data = serialize_page(pages[0])
            filename = f"page-{pages[0].slug.replace('/', '-')}.json"
        else:
            data = [serialize_page(p) for p in pages]
            filename = "pages-export.json"

        response = HttpResponse(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    # ========================
    # Bulk Actions
    # ========================

    @admin.action(description="Submit selected drafts for review")
    def action_submit_for_review(self, request, queryset):
        count = 0
        for page in queryset.filter(status="draft"):
            try:
                page.submit_for_review(user=request.user)
                count += 1
            except ValueError:
                pass
        self.message_user(request, f"{count} page(s) submitted for review.", messages.SUCCESS)

    @admin.action(description="Publish selected pages")
    def action_publish(self, request, queryset):
        count = 0
        for page in queryset.filter(status__in=["review", "draft"]):
            try:
                page.publish(user=request.user)
                count += 1
            except ValueError:
                pass
        self.message_user(request, f"{count} page(s) published.", messages.SUCCESS)

    @admin.action(description="Unpublish selected pages")
    def action_unpublish(self, request, queryset):
        count = 0
        for page in queryset.filter(status="published"):
            page.unpublish(user=request.user)
            count += 1
        self.message_user(request, f"{count} page(s) unpublished.", messages.WARNING)
