from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from core.admin.base import BaseModelAdmin
from core.models import SMSServiceConfig

from ..helpers import _normalize_phone_number, _send_test_sms
from ..test_send_mixin import TestSendViewsMixin


class SMSServiceConfigForm(forms.ModelForm):
    class Meta:
        model = SMSServiceConfig
        fields = "__all__"
        widgets = {
            "auth_token": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }


@admin.register(SMSServiceConfig)
class SMSServiceConfigAdmin(TestSendViewsMixin, BaseModelAdmin):
    form = SMSServiceConfigForm
    list_display = ("name", "status_badge", "account_sid", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "account_sid")
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config", "test_send_action"]
    actions_list = ["test_email_list", "test_sms_list"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("Twilio Verify"),
            {
                "fields": ("account_sid", "auth_token", "verify_sid", "from_number"),
                "description": "Twilio credentials for SMS phone verification (Verify API).",
            },
        ),
        (_("Info"), {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)

    @display(description="Status", label=True)
    def status_badge(self, obj):
        if obj.is_active:
            return "Active", "success"
        return "Inactive", "danger"

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = SMSServiceConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active SMS config.')
        return HttpResponseRedirect(reverse("admin:core_smsserviceconfig_change", args=[object_id]))

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/test-send/",
                self.admin_site.admin_view(self.test_send_view),
                name="core_smsserviceconfig_test_send",
            ),
        ]
        custom_urls += self._get_test_send_urls("core_smsserviceconfig")
        return custom_urls + super().get_urls()

    @action(description="Send test SMS", url_path="test-send", icon="send")
    def test_send_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:core_smsserviceconfig_test_send", args=[object_id]))

    def test_send_view(self, request, object_id):
        obj = SMSServiceConfig.objects.get(pk=object_id)
        change_url = reverse("admin:core_smsserviceconfig_change", args=[object_id])

        if request.method == "POST":
            country_code = request.POST.get("country_code", "+1")
            recipient = request.POST.get("recipient", "").strip()
            if not recipient:
                messages.error(request, "Please provide a phone number.")
                return HttpResponseRedirect(request.path)
            full_number = _normalize_phone_number(country_code, recipient)
            try:
                result = _send_test_sms(config=obj, phone_number=full_number)
                messages.success(request, f"Test SMS sent to {full_number}: {result}.")
            except Exception as exc:
                messages.error(request, f"Failed to send test SMS: {exc}")
            return HttpResponseRedirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Send Test SMS — {obj.name}",
            "input_label": "Recipient phone number",
            "input_type": "tel",
            "input_placeholder": "2345678901",
            "input_help": "Select country code and enter the phone number.",
            "submit_label": "Send Test SMS",
            "cancel_url": change_url,
        }
        return TemplateResponse(request, "admin/core/test_send_form.html", context)
