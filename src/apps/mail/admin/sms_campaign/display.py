"""Broadcast SMS campaign admin."""

from django.utils.html import escape, format_html
from unfold.decorators import display


class SmsCampaignDisplayMixin:
    """SmsCampaignAdmin's list columns and read-only message display."""

    @display(description="Campaign")
    def name_preview(self, obj):
        return obj.name[:60] + "..." if len(obj.name) > 60 else obj.name

    @display(description="Audience", label=True)
    def audience_badge(self, obj):
        badge_colors = {
            "subscribers": ("Subscribers", "info"),
            "event_registrants": ("Event", "warning"),
            "ticket_type": ("Ticket Type", "warning"),
            "checked_in": ("Checked In", "success"),
            "not_checked_in": ("No-Shows", "danger"),
            "all_members": ("All Members", "info"),
            "staff": ("Staff", "info"),
            "selected_members": ("Selected", "info"),
            "manual": ("Manual", "info"),
        }
        return badge_colors.get(obj.audience_type, (obj.get_audience_type_display(), "info"))

    @display(description="Phone Eligibility", label=True)
    def phone_policy_badge(self, obj):
        if obj.phone_policy == "verified_opt_in":
            return "Verified opt-ins", "success"
        return "Any verified", "warning"

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {"draft": "info", "sending": "warning", "partial": "warning", "sent": "success", "failed": "danger"}
        return obj.get_status_display(), colors.get(obj.status, "info")

    @display(description="SMS Message")
    def message_readonly(self, obj):
        if not obj:
            return "-"
        return format_html(
            '<pre class="max-h-[70vh] max-w-2xl overflow-auto whitespace-pre-wrap break-words '
            "rounded-default border border-base-200 bg-base-50 px-3 py-2 font-mono text-sm font-medium "
            'text-font-default-light shadow-xs dark:border-base-700 dark:bg-base-800 dark:text-font-default-dark">'
            "{message}</pre>",
            message=escape(obj.message or ""),
        )
