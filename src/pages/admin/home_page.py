from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline

from ..models import HomePage, PageComponent
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

    actions = ["action_submit_for_review", "action_publish", "action_unpublish"]

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
