from uuid import uuid4

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.core.signing import TimestampSigner
from django.http import HttpResponseRedirect
from django.utils.html import format_html


class WorkflowAdminMixin:
    """
    Shared admin logic for Page and HomePage.

    Subclasses must override get_display_name(obj) to return the appropriate
    display name (e.g. obj.name for HomePage, obj.title for Page).
    """

    def get_display_name(self, obj):
        """Return display name for messages. Override in subclass."""
        return str(obj)

    def status_badge(self, obj):
        colors = {"draft": "#6c757d", "review": "#f0ad4e", "scheduled": "#0d6efd", "published": "#5cb85c"}
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
        super().save_model(request, obj, form, change)
        if change:
            obj.save_version(comment=f"Edited via admin by {request.user}", user=request.user)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as e:
            # Model-level ValidationError (e.g. from save()) — show as a
            # user-friendly error message instead of a 500 error page.
            error_messages = e.messages if hasattr(e, "messages") else [str(e)]
            for msg in error_messages:
                self.message_user(request, msg, messages.ERROR)
            return HttpResponseRedirect(request.path)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj:
            extra_context["versions"] = obj.get_versions()[:20]
            extra_context["current_status"] = obj.status

            # Generate preview token signed with object ID
            signer = TimestampSigner()
            extra_context["preview_token"] = signer.sign(str(obj.pk))

            # Pass frontend URL to template
            from django.conf import settings

            extra_context["frontend_url"] = getattr(settings, "FRONTEND_URL", "")
            extra_context["object_id"] = str(obj.pk)
            extra_context["preview_session_id"] = str(uuid4())

        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def response_change(self, request, obj):
        name = self.get_display_name(obj)

        if "_submit_for_review" in request.POST:
            try:
                obj.submit_for_review(user=request.user)
                self.message_user(request, f'"{name}" submitted for review.', messages.SUCCESS)
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_publish" in request.POST:
            try:
                obj.publish(user=request.user)
                self.message_user(request, f'"{name}" has been published.', messages.SUCCESS)
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_unpublish" in request.POST:
            obj.unpublish(user=request.user)
            self.message_user(request, f'"{name}" has been unpublished.', messages.WARNING)
            return HttpResponseRedirect(request.path)

        if "_reject_review" in request.POST:
            try:
                obj.reject_review(user=request.user)
                self.message_user(request, f'"{name}" review rejected.', messages.WARNING)
            except ValueError as e:
                self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_schedule_publish" in request.POST:
            schedule_dt = request.POST.get("_schedule_datetime")
            if schedule_dt:
                try:
                    from django.utils import timezone as tz
                    from django.utils.dateparse import parse_datetime

                    dt = parse_datetime(schedule_dt)
                    if dt and tz.is_naive(dt):
                        dt = tz.make_aware(dt)
                    if dt:
                        obj.schedule_publish(dt, user=request.user)
                        self.message_user(
                            request,
                            f'"{name}" scheduled for publishing at {dt.strftime("%b %d, %Y %I:%M %p")}.',
                            messages.SUCCESS,
                        )
                    else:
                        self.message_user(request, "Invalid date/time format.", messages.ERROR)
                except ValueError as e:
                    self.message_user(request, str(e), messages.ERROR)
            else:
                self.message_user(request, "Please select a date and time.", messages.WARNING)
            return HttpResponseRedirect(request.path)

        if "_rollback" in request.POST:
            version_number = request.POST.get("_rollback")
            if version_number:
                try:
                    obj.rollback(int(version_number), user=request.user)
                    self.message_user(request, f'"{name}" rolled back to version {version_number}.', messages.SUCCESS)
                except ValueError as e:
                    self.message_user(request, str(e), messages.ERROR)
            return HttpResponseRedirect(request.path)

        return super().response_change(request, obj)

    @admin.action(description="Submit selected drafts for review")
    def action_submit_for_review(self, request, queryset):
        count = 0
        for obj in queryset.filter(status="draft"):
            try:
                obj.submit_for_review(user=request.user)
                count += 1
            except ValueError:
                pass
        self.message_user(request, f"{count} item(s) submitted for review.", messages.SUCCESS)

    @admin.action(description="Publish selected items")
    def action_publish(self, request, queryset):
        count = 0
        for obj in queryset.filter(status__in=["review", "draft"]):
            try:
                obj.publish(user=request.user)
                count += 1
            except ValueError:
                pass
        self.message_user(request, f"{count} item(s) published.", messages.SUCCESS)

    @admin.action(description="Unpublish selected items")
    def action_unpublish(self, request, queryset):
        count = 0
        for obj in queryset.filter(status="published"):
            obj.unpublish(user=request.user)
            count += 1
        self.message_user(request, f"{count} item(s) unpublished.", messages.WARNING)
