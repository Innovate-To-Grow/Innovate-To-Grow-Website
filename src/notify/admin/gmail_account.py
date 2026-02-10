"""
Admin configuration for GoogleGmailAccount.

Provides management UI for Gmail SMTP accounts with password masking,
test-connection action, and operational metadata display.
"""

import smtplib

from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from notify.models import GoogleGmailAccount


class GmailAccountForm(forms.ModelForm):
    """Custom form that masks the password field in the admin."""

    password = forms.CharField(
        widget=forms.PasswordInput(render_value=True),
        help_text="Google App Password (16 characters, spaces ignored).",
    )

    class Meta:
        model = GoogleGmailAccount
        fields = "__all__"


@admin.register(GoogleGmailAccount)
class GoogleGmailAccountAdmin(admin.ModelAdmin):
    """Admin for managing Gmail SMTP accounts."""

    form = GmailAccountForm

    list_display = (
        "gmail_address",
        "display_name",
        "is_active_badge",
        "is_default_badge",
        "smtp_host",
        "smtp_port",
        "last_used_at",
    )
    list_filter = ("is_active", "is_default", "smtp_host")
    search_fields = ("gmail_address", "display_name")
    readonly_fields = ("id", "last_used_at", "last_error", "created_at", "updated_at")
    actions = ["test_connection", "set_as_default"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "gmail_address",
                    "password",
                    "display_name",
                    "is_active",
                    "is_default",
                ),
            },
        ),
        (
            "SMTP Settings",
            {
                "fields": ("smtp_host", "smtp_port", "use_tls"),
                "classes": ("collapse",),
                "description": "Only change these if you use a non-Gmail SMTP server.",
            },
        ),
        (
            "Operational Info",
            {
                "fields": ("last_used_at", "last_error"),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("id", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    @admin.display(description="Active", boolean=True, ordering="is_active")
    def is_active_badge(self, obj):
        return obj.is_active

    @admin.display(description="Default", boolean=True, ordering="is_default")
    def is_default_badge(self, obj):
        return obj.is_default

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @admin.action(description="Test SMTP connection for selected accounts")
    def test_connection(self, request, queryset):
        """Attempt an SMTP login to verify credentials."""
        for account in queryset:
            try:
                if account.use_tls:
                    server = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=10)
                    server.starttls()
                else:
                    server = smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, timeout=10)
                server.login(account.gmail_address, account.password)
                server.quit()
                self.message_user(
                    request,
                    format_html(
                        '<strong>{}</strong>: Connection successful!',
                        account.gmail_address,
                    ),
                    messages.SUCCESS,
                )
                account.mark_used()
            except Exception as exc:
                error_msg = str(exc)
                self.message_user(
                    request,
                    format_html(
                        '<strong>{}</strong>: Connection FAILED - {}',
                        account.gmail_address,
                        error_msg,
                    ),
                    messages.ERROR,
                )
                account.mark_used(error=error_msg)

    @admin.action(description="Set selected account as default")
    def set_as_default(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one account to set as default.",
                messages.WARNING,
            )
            return
        account = queryset.first()
        account.is_default = True
        account.save()
        self.message_user(
            request,
            f"{account.gmail_address} is now the default sender.",
            messages.SUCCESS,
        )
