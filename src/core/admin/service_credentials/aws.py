import logging

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminPasswordToggleWidget, UnfoldAdminSelectWidget

from core.admin.base import BaseModelAdmin
from core.models import AWSCredentialConfig

logger = logging.getLogger(__name__)


class AWSCredentialConfigForm(forms.ModelForm):
    default_model_id = forms.TypedChoiceField(
        coerce=str,
        required=False,
        label="Default AI Model",
        help_text="Site-wide default Bedrock model or inference profile ID.",
        widget=UnfoldAdminSelectWidget,
    )

    class Meta:
        model = AWSCredentialConfig
        fields = "__all__"
        widgets = {
            "secret_access_key": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from core.services.bedrock import get_available_models

            grouped = get_available_models()
            choices = [("", "---------")]
            for group, models in grouped:
                choices.append((group, list(models)))
            self.fields["default_model_id"].choices = choices
        except Exception:
            logger.debug("Could not fetch Bedrock models for form choices", exc_info=True)
            current = self.initial.get("default_model_id", "") or ""
            if current:
                self.fields["default_model_id"].choices = [("", "---------"), (current, current)]
            else:
                self.fields["default_model_id"].choices = [("", "---------")]


@admin.register(AWSCredentialConfig)
class AWSCredentialConfigAdmin(BaseModelAdmin):
    form = AWSCredentialConfigForm
    list_display = ("name", "status_badge", "configured_badge", "access_key_masked", "default_region", "default_model_display", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "access_key_id")
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config", "test_bedrock_api"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("AWS Credentials"),
            {
                "fields": ("access_key_id", "secret_access_key", "default_region"),
                "description": "IAM access key used by AWS services (SES, S3, etc.).",
            },
        ),
        (
            _("Default AI Model"),
            {
                "fields": ("default_model_id",),
                "description": "Default Bedrock model used site-wide. "
                "Model list is fetched from AWS using the credentials above.",
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

    @display(description="Default Model")
    def default_model_display(self, obj):
        if not obj.default_model_id:
            return "—"
        try:
            from core.services.bedrock import get_available_models

            for _group, models in get_available_models():
                for mid, name in models:
                    if mid == obj.default_model_id:
                        return name
        except Exception:
            pass
        return obj.default_model_id

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

        model_id = obj.default_model_id
        if not model_id:
            messages.error(request, "Cannot test: no default AI model selected.")
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
