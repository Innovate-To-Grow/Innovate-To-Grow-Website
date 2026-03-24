import json
import logging

from django import forms
from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from sheets.models import SheetsAccount

logger = logging.getLogger(__name__)

REQUIRED_SA_KEYS = {"type", "project_id", "private_key", "client_email"}


class SheetsAccountForm(forms.ModelForm):
    class Meta:
        model = SheetsAccount
        fields = "__all__"
        widgets = {
            "service_account_json": forms.Textarea(attrs={"rows": 6, "cols": 80}),
        }

    def clean_service_account_json(self):
        raw = self.cleaned_data.get("service_account_json", "")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Invalid JSON: {exc}") from exc

        missing = REQUIRED_SA_KEYS - set(data.keys())
        if missing:
            raise forms.ValidationError(f"Missing required keys: {', '.join(sorted(missing))}")
        return raw


@admin.register(SheetsAccount)
class SheetsAccountAdmin(ModelAdmin):
    form = SheetsAccountForm

    list_display = ("email", "display_name", "is_active_badge", "last_used_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("email", "display_name")
    readonly_fields = ("id", "last_used_at", "last_error", "created_at", "updated_at")
    actions = ["test_connection", "set_as_active"]

    fieldsets = (
        (None, {"fields": ("email", "display_name", "is_active")}),
        (
            "Credentials",
            {
                "fields": ("service_account_json",),
                "classes": ("collapse",),
                "description": "Service account JSON key from Google Cloud Console.",
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

    @admin.display(description="Active", boolean=True, ordering="is_active")
    def is_active_badge(self, obj):
        return obj.is_active

    @admin.action(description="Test connection")
    def test_connection(self, request, queryset):
        from sheets.services.client import get_client_for_account

        for account in queryset:
            try:
                client = get_client_for_account(account)
                # A simple API call to verify credentials work
                client.spreadsheets().get(spreadsheetId="__test__").execute()
            except Exception as exc:  # noqa: BLE001
                error_msg = str(exc)
                if "404" in error_msg or "not found" in error_msg.lower():
                    messages.success(
                        request, f"{account.email}: credentials valid (test spreadsheet not found, as expected)."
                    )
                else:
                    messages.error(request, f"{account.email}: {error_msg}")

    @admin.action(description="Set as active")
    def set_as_active(self, request, queryset):
        if queryset.count() != 1:
            messages.error(request, "Select exactly one account to set as active.")
            return
        account = queryset.first()
        account.is_active = True
        account.save()
        messages.success(request, f"{account.email} is now the active account.")
