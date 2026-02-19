from django.contrib import admin
from django.utils import timezone
from unfold.admin import ModelAdmin

from ..models import FormSubmission, UniformForm


@admin.register(UniformForm)
class UniformFormAdmin(ModelAdmin):
    """Admin interface for managing form definitions."""

    list_display = ("name", "slug", "is_active", "published", "submission_count", "updated_at")
    list_filter = ("is_active", "published", "created_at")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("form_uuid", "submission_count", "created_at", "updated_at")

    fieldsets = (
        ("Basic Information", {"fields": ("name", "slug", "description", "form_uuid")}),
        (
            "Form Fields Configuration",
            {
                "fields": ("fields",),
                "classes": ("extrapretty",),
                "description": "Define form fields as JSON array. Each field should have: id, field_type, name, label, required, order, and optional validation rules.",
            },
        ),
        ("Form Settings", {"fields": ("submit_button_text", "success_message", "redirect_url")}),
        (
            "Email Notifications",
            {
                "fields": ("enable_email_notification", "notification_recipients", "email_subject_template"),
                "classes": ("collapse",),
            },
        ),
        ("Submission Rules", {"fields": ("allow_anonymous", "login_required", "max_submissions_per_user")}),
        ("Publishing", {"fields": ("is_active", "published")}),
        ("Statistics", {"fields": ("submission_count", "created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(FormSubmission)
class FormSubmissionAdmin(ModelAdmin):
    """Admin interface for viewing and managing form submissions."""

    list_display = ("get_form_name", "get_user_display", "status", "created_at", "notification_sent")
    list_filter = ("status", "form", "notification_sent", "created_at")
    search_fields = ("admin_notes", "user__username", "user__email", "ip_address")
    readonly_fields = (
        "submission_uuid",
        "form",
        "user",
        "data",
        "created_at",
        "ip_address",
        "user_agent",
        "referrer",
        "notification_sent_at",
    )
    date_hierarchy = "created_at"

    fieldsets = (
        ("Submission Information", {"fields": ("submission_uuid", "form", "user", "created_at")}),
        ("Submitted Data", {"fields": ("data",), "classes": ("extrapretty",)}),
        ("Status & Review", {"fields": ("status", "admin_notes", "reviewed_by", "reviewed_at")}),
        ("Metadata", {"fields": ("ip_address", "user_agent", "referrer"), "classes": ("collapse",)}),
        (
            "Email Notification",
            {"fields": ("notification_sent", "notification_sent_at", "notification_error"), "classes": ("collapse",)},
        ),
    )

    actions = ["mark_as_reviewed", "mark_as_spam", "mark_as_processed"]

    def get_form_name(self, obj):
        """Display the form name."""
        return obj.form.name

    get_form_name.short_description = "Form"
    get_form_name.admin_order_field = "form__name"

    def get_user_display(self, obj):
        """Display user info or 'Anonymous'."""
        if obj.user:
            return obj.user.username
        return "Anonymous"

    get_user_display.short_description = "User"
    get_user_display.admin_order_field = "user__username"

    def mark_as_reviewed(self, request, queryset):
        """Mark selected submissions as reviewed."""
        count = 0
        for submission in queryset:
            if submission.status == FormSubmission.STATUS_PENDING:
                submission.mark_as_reviewed(request.user)
                count += 1
        self.message_user(request, f"{count} submission(s) marked as reviewed.")

    mark_as_reviewed.short_description = "Mark selected as reviewed"

    def mark_as_spam(self, request, queryset):
        """Mark selected submissions as spam."""
        count = queryset.update(status=FormSubmission.STATUS_SPAM, updated_at=timezone.now())
        self.message_user(request, f"{count} submission(s) marked as spam.")

    mark_as_spam.short_description = "Mark selected as spam"

    def mark_as_processed(self, request, queryset):
        """Mark selected submissions as processed."""
        count = queryset.update(status=FormSubmission.STATUS_PROCESSED, updated_at=timezone.now())
        self.message_user(request, f"{count} submission(s) marked as processed.")

    mark_as_processed.short_description = "Mark selected as processed"

    def has_add_permission(self, request):
        """Only superusers can manually add submissions via admin."""
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        """Superusers and staff can edit submissions."""
        return request.user.is_staff or request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete submissions."""
        return request.user.is_superuser
