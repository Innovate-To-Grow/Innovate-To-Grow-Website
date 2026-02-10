from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils.html import format_html

from ..models import Page, PageComponent
from .page_component import PageComponentForm


class PageComponentInline(admin.StackedInline):
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
        "css_code",
        "js_code",
        "config",
        "form",
        "image",
        "image_alt",
        "background_image",
        "data_source",
        "data_params",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("order", "id")
    show_change_link = True


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    inlines = [PageComponentInline]
    change_form_template = "admin/pages/page/change_form.html"
    list_display = ("title", "slug", "status_badge", "view_count", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = (
        "page_uuid",
        "slug_depth",
        "view_count",
        "last_viewed_at",
        "created_at",
        "updated_at",
        "status",
        "published_at",
        "published_by",
        "submitted_for_review_at",
        "submitted_for_review_by",
    )

    fieldsets = (
        ("Basic Information", {"fields": ("title", "slug", "page_uuid")}),
        ("Rendering", {"fields": ("template_name",), "classes": ("extrapretty",)}),
        (
            "SEO & Metadata",
            {
                "fields": (
                    "meta_title",
                    "meta_description",
                    "meta_keywords",
                    "og_image",
                    "canonical_url",
                    "meta_robots",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Publishing Workflow",
            {
                "fields": (
                    "status",
                    "published_at",
                    "published_by",
                    "submitted_for_review_at",
                    "submitted_for_review_by",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
        (
            "Statistics",
            {"fields": ("view_count", "last_viewed_at", "slug_depth"), "classes": ("collapse",)},
        ),
    )

    actions = ["action_submit_for_review", "action_publish", "action_unpublish"]

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
