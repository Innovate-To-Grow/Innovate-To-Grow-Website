from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from apps.core.admin.base import BaseModelAdmin
from apps.core.models import AWSCredentialConfig

from ..test_send_mixin import TestSendViewsMixin


class AWSCredentialConfigForm(forms.ModelForm):
    class Meta:
        model = AWSCredentialConfig
        fields = "__all__"
        widgets = {
            "secret_access_key": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }


@admin.register(AWSCredentialConfig)
class AWSCredentialConfigAdmin(TestSendViewsMixin, BaseModelAdmin):
    form = AWSCredentialConfigForm
    list_display = (
        "name",
        "status_badge",
        "configured_badge",
        "access_key_masked",
        "default_region",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "access_key_id")
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config", "test_bedrock_api"]
    actions_list = ["test_email_list", "test_sms_list"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("AWS Credentials"),
            {
                "fields": ("access_key_id", "secret_access_key", "default_region"),
                "description": "Shared IAM access key and AWS region used by SES email, SNS SMS, and Bedrock.",
            },
        ),
        (
            _("SNS SMS"),
            {
                "fields": ("sms_from_number", "sms_message_template"),
                "description": "SNS origination number and OTP template used for phone verification.",
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

    @display(description="Configured", label=True)
    def configured_badge(self, obj):
        if obj.is_configured:
            return "Yes", "success"
        return "No", "warning"

    @display(description="Access Key ID")
    def access_key_masked(self, obj):
        if obj.access_key_id:
            return f"...{obj.access_key_id[-4:]}"
        return "—"

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = AWSCredentialConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active AWS credential config.')
        return HttpResponseRedirect(reverse("admin:core_awscredentialconfig_change", args=[object_id]))

    @action(description="Test Bedrock API", url_path="test-bedrock", icon="science")
    def test_bedrock_api(self, request, object_id):
        """Send a minimal Converse call to verify credentials + model work."""
        import boto3
        from botocore.exceptions import ClientError

        obj = AWSCredentialConfig.objects.get(pk=object_id)
        change_url = reverse("admin:core_awscredentialconfig_change", args=[object_id])

        if not obj.is_configured:
            messages.error(request, "Cannot test: AWS credentials are not configured.")
            return HttpResponseRedirect(change_url)

        from apps.system_intelligence.models import SystemIntelligenceConfig

        model_id = SystemIntelligenceConfig.load().default_model_id
        if not model_id:
            messages.error(request, "Cannot test: no default AI model selected in System Intelligence Config.")
            return HttpResponseRedirect(change_url)

        try:
            client = boto3.client(
                "bedrock-runtime",
                region_name=obj.default_region or "us-west-2",
                aws_access_key_id=obj.access_key_id,
                aws_secret_access_key=obj.secret_access_key,
            )
            resp = client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": "Reply with exactly: OK"}]}],
                inferenceConfig={"maxTokens": 16, "temperature": 0},
            )
            output_text = resp["output"]["message"]["content"][0]["text"]
            messages.success(request, 'Bedrock API test passed. Model responded: "' + output_text.strip() + '"')
        except ClientError as exc:
            messages.error(request, f"Bedrock API test failed: {exc.response['Error']['Message']}")
        except Exception as exc:
            messages.error(request, f"Bedrock API test failed: {exc}")

        return HttpResponseRedirect(change_url)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_urls(self):
        custom_urls = self._get_test_send_urls("core_awscredentialconfig")
        return custom_urls + super().get_urls()
