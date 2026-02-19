from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from ..models import VerificationRequest


@admin.register(VerificationRequest)
class VerificationRequestAdmin(ModelAdmin):
    """
    Enhanced admin for verification requests with detailed management.
    """

    list_display = (
        "id",
        "channel_badge",
        "method_badge",
        "target",
        "purpose",
        "token_display",
        "verification_link",
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
        "full_verification_link",
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
                "fields": ("code", "token", "full_verification_link"),
                "description": "The code or token used for verification. Copy the link to verify the email.",
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
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px;">{}</span>',
            color,
            obj.get_channel_display(),
        )

    @admin.display(description="Method")
    def method_badge(self, obj):
        colors = {"code": "#9b59b6", "link": "#e67e22"}
        color = colors.get(obj.method, "#7f8c8d")
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px;">{}</span>',
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
            '<span style="background:{}; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px;">{}</span>',
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
            return format_html('<span style="color:#27ae60;">{} min</span>', minutes)
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

    @admin.display(description="Token")
    def token_display(self, obj):
        """Display token with copy functionality."""
        if obj.token:
            short_token = obj.token[:8] + "..." if len(obj.token) > 8 else obj.token
            return format_html(
                '<code style="background:#f5f5f5; padding:2px 6px; border-radius:3px; font-size:11px;" '
                'title="Click to see full token: {}">{}</code>',
                obj.token,
                short_token,
            )
        elif obj.code:
            return format_html(
                '<code style="background:#e8f4e8; padding:2px 6px; border-radius:3px; font-size:12px; font-weight:bold;">{}</code>',
                obj.code,
            )
        return format_html('<span style="color:#95a5a6;">—</span>')

    @admin.display(description="Verify Link")
    def verification_link(self, obj):
        """Display a clickable verification link for testing."""
        if obj.token and obj.status == VerificationRequest.STATUS_PENDING:
            # Construct verification URL (adjust base URL as needed)
            verify_url = f"/verify-email/{obj.token}"
            return format_html(
                '<a href="{}" target="_blank" style="color:#3498db; text-decoration:none;" '
                'title="Open verification link in new tab">🔗 Open</a>',
                verify_url,
            )
        return format_html('<span style="color:#95a5a6;">—</span>')

    @admin.display(description="Full Verification Link")
    def full_verification_link(self, obj):
        """Display the full verification link for copying."""
        if obj.token:
            verify_url = f"/verify-email/{obj.token}"
            return format_html(
                '<div style="background:#f8f9fa; padding:10px; border-radius:4px; margin:5px 0;">'
                "<strong>Token:</strong><br>"
                '<code style="word-break:break-all; font-size:12px;">{}</code>'
                "<br><br>"
                "<strong>Verification URL:</strong><br>"
                '<code style="word-break:break-all; font-size:12px;">{}</code>'
                "<br><br>"
                '<a href="{}" target="_blank" style="display:inline-block; background:#3498db; color:#fff; '
                'padding:8px 16px; border-radius:4px; text-decoration:none; margin-top:5px;">Open Verification Link</a>'
                "</div>",
                obj.token,
                verify_url,
                verify_url,
            )
        elif obj.code:
            return format_html(
                '<div style="background:#f8f9fa; padding:10px; border-radius:4px;">'
                "<strong>Verification Code:</strong><br>"
                '<code style="font-size:18px; font-weight:bold; letter-spacing:2px;">{}</code>'
                "</div>",
                obj.code,
            )
        return "No verification credentials available."
