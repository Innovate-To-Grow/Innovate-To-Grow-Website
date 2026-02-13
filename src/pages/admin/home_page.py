import json

from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline

from ..models import HomePage, PageComponent
from .import_export import deserialize_homepage, serialize_homepage
from .page_component import PageComponentForm


class HomePageComponentInline(StackedInline):
    model = PageComponent
    fk_name = "home_page"
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


@admin.register(HomePage)
class HomePageAdmin(ModelAdmin):
    inlines = [HomePageComponentInline]
    change_form_template = "admin/pages/homepage/change_form.html"
    change_list_template = "admin/pages/homepage/change_list.html"
    list_display = ("name", "is_active", "status_badge", "component_count", "created_at", "updated_at")
    list_filter = ("is_active", "status", "created_at")
    search_fields = ("name",)
    readonly_fields = (
        "status",
        "published_at",
        "published_by",
    )

    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (
            "Publishing",
            {
                "fields": ("status", "published_at", "published_by"),
            },
        ),
    )

    actions = ["action_submit_for_review", "action_publish", "action_unpublish", "action_export_json"]

    def component_count(self, obj):
        return obj.components.count()

    component_count.short_description = "Components"

    def status_badge(self, obj):
        """Display a colored status badge."""
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
        """Handle custom workflow button clicks."""

        if "_submit_for_review" in request.POST:
            try:
                obj.submit_for_review(user=request.user)
                self.message_user(request, f'"{obj.name}" submitted for review.', messages.SUCCESS)
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_publish" in request.POST:
            try:
                obj.publish(user=request.user)
                self.message_user(request, f'"{obj.name}" has been published.', messages.SUCCESS)
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_unpublish" in request.POST:
            obj.unpublish(user=request.user)
            self.message_user(request, f'"{obj.name}" has been unpublished.', messages.WARNING)
            return HttpResponseRedirect(request.path)

        if "_reject_review" in request.POST:
            try:
                obj.reject_review(user=request.user)
                self.message_user(request, f'"{obj.name}" review rejected.', messages.WARNING)
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
                        f'"{obj.name}" rolled back to version {version_number}.',
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
                name="pages_homepage_import",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_url"] = reverse("admin:pages_homepage_import")
        return super().changelist_view(request, extra_context=extra_context)

    def import_view(self, request):
        """Handle JSON import for HomePages."""
        context = {**self.admin_site.each_context(request), "title": "Import HomePage JSON"}

        if request.method == "POST":
            json_file = request.FILES.get("json_file")
            if not json_file:
                context["error"] = "No file uploaded."
                return TemplateResponse(request, "admin/pages/homepage/import_form.html", context)

            try:
                data = json.load(json_file)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                context["error"] = f"Invalid JSON file: {e}"
                return TemplateResponse(request, "admin/pages/homepage/import_form.html", context)

            # Support both single homepage and array
            items = data if isinstance(data, list) else [data]
            all_warnings = []
            imported_count = 0

            for item in items:
                if item.get("export_type") != "homepage":
                    all_warnings.append(
                        f"Skipped entry with export_type='{item.get('export_type')}' (expected 'homepage')."
                    )
                    continue
                try:
                    homepage, warnings = deserialize_homepage(item, user=request.user)
                    all_warnings.extend(warnings)
                    imported_count += 1
                except Exception as e:
                    all_warnings.append(f"Error importing homepage: {e}")

            if imported_count:
                self.message_user(
                    request,
                    f"Successfully imported {imported_count} home page(s).",
                    messages.SUCCESS,
                )
            if all_warnings:
                context["warnings"] = all_warnings
                return TemplateResponse(request, "admin/pages/homepage/import_form.html", context)

            return HttpResponseRedirect(reverse("admin:pages_homepage_changelist"))

        return TemplateResponse(request, "admin/pages/homepage/import_form.html", context)

    @admin.action(description="Export selected home pages as JSON")
    def action_export_json(self, request, queryset):
        homepages = list(queryset)
        if len(homepages) == 1:
            data = serialize_homepage(homepages[0])
            filename = f"homepage-{homepages[0].name.replace(' ', '-').lower()}.json"
        else:
            data = [serialize_homepage(hp) for hp in homepages]
            filename = "homepages-export.json"

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
        for hp in queryset.filter(status="draft"):
            try:
                hp.submit_for_review(user=request.user)
                count += 1
            except ValueError:
                pass
        self.message_user(request, f"{count} home page(s) submitted for review.", messages.SUCCESS)

    @admin.action(description="Publish selected home pages")
    def action_publish(self, request, queryset):
        count = 0
        for hp in queryset.filter(status__in=["review", "draft"]):
            try:
                hp.publish(user=request.user)
                count += 1
            except ValueError:
                pass
        self.message_user(request, f"{count} home page(s) published.", messages.SUCCESS)

    @admin.action(description="Unpublish selected home pages")
    def action_unpublish(self, request, queryset):
        count = 0
        for hp in queryset.filter(status="published"):
            hp.unpublish(user=request.user)
            count += 1
        self.message_user(request, f"{count} home page(s) unpublished.", messages.WARNING)
