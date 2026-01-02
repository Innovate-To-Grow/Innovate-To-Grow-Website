from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from ..models import VerificationRequest


@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):
    """
    Enhanced admin for verification requests with detailed management.
    """

    list_display = (
        "id",
        "channel_badge",
        "method_badge",
        "target",
        "purpose",
        "status_badge",
        "attempts_display",
        "expires_display",
        "created_at",
    )
    list_filter = ("channel", "method", "status", "purpose", "created_at", "expires_at")
    search_fields = ("target", "code", "token", "purpose")
    readonly_fields = (
        "created_at",
        "updated_at",
        "verified_at",
        "attempts",
        "time_remaining",
        "is_expired",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    list_select_related = True
    save_on_top = True

    fieldsets = (
        (
            "Basic Info",
            {
                "fields": ("channel", "method", "target", "purpose"),
                "description": "Core verification request details.",
            },
        ),
        (
            "Verification Credentials",
            {
                "fields": ("code", "token"),
                "classes": ("collapse",),
                "description": "The code or token used for verification.",
            },
        ),
        (
            "Status & Attempts",
            {
                "fields": (
                    "status",
                    "attempts",
                    "max_attempts",
                    "is_expired",
                    "time_remaining",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("expires_at", "verified_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["mark_as_expired", "mark_as_failed", "reset_attempts"]

    @admin.display(description="Channel")
    def channel_badge(self, obj):
        colors = {"email": "#3498db", "sms": "#27ae60"}
        color = colors.get(obj.channel, "#7f8c8d")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            color,
            obj.get_channel_display(),
        )

    @admin.display(description="Method")
    def method_badge(self, obj):
        colors = {"code": "#9b59b6", "link": "#e67e22"}
        color = colors.get(obj.method, "#7f8c8d")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            color,
            obj.get_method_display(),
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "pending": "#f39c12",
            "verified": "#27ae60",
            "expired": "#95a5a6",
            "failed": "#e74c3c",
        }
        color = colors.get(obj.status, "#7f8c8d")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Attempts")
    def attempts_display(self, obj):
        if obj.attempts >= obj.max_attempts:
            return format_html(
                '<span style="color:#e74c3c; font-weight:bold;">{}/{}</span>',
                obj.attempts,
                obj.max_attempts,
            )
        return f"{obj.attempts}/{obj.max_attempts}"

    @admin.display(description="Expires")
    def expires_display(self, obj):
        if not obj.expires_at:
            return format_html('<span style="color:#95a5a6;">—</span>')
        now = timezone.now()
        if obj.expires_at <= now:
            return format_html('<span style="color:#e74c3c;">Expired</span>')
        delta = obj.expires_at - now
        minutes = int(delta.total_seconds() // 60)
        if minutes < 60:
            return format_html(
                '<span style="color:#27ae60;">{} min</span>', minutes
            )
        hours = minutes // 60
        return format_html('<span style="color:#f39c12;">{} hr</span>', hours)

    @admin.display(description="Time Remaining", boolean=False)
    def time_remaining(self, obj):
        if not obj.expires_at:
            return "—"
        now = timezone.now()
        if obj.expires_at <= now:
            return "Expired"
        delta = obj.expires_at - now
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        return f"{minutes}m {seconds}s"

    @admin.display(description="Is Expired", boolean=True)
    def is_expired(self, obj):
        if not obj.expires_at:
            return None
        return obj.expires_at <= timezone.now()

    @admin.action(description="Mark selected as expired")
    def mark_as_expired(self, request, queryset):
        updated = queryset.update(status=VerificationRequest.STATUS_EXPIRED)
        self.message_user(request, f"{updated} verification(s) marked as expired.")

    @admin.action(description="Mark selected as failed")
    def mark_as_failed(self, request, queryset):
        updated = queryset.update(status=VerificationRequest.STATUS_FAILED)
        self.message_user(request, f"{updated} verification(s) marked as failed.")

    @admin.action(description="Reset attempts to 0")
    def reset_attempts(self, request, queryset):
        updated = queryset.update(attempts=0, status=VerificationRequest.STATUS_PENDING)
        self.message_user(request, f"{updated} verification(s) had attempts reset.")



