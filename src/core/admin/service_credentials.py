import logging

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import action, display
from unfold.widgets import (
    UnfoldAdminFileFieldWidget,
    UnfoldAdminPasswordToggleWidget,
    UnfoldAdminTextareaWidget,
)

from core.models import EmailServiceConfig, GmailImportConfig, GoogleCredentialConfig, SMSServiceConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


class EmailServiceConfigForm(forms.ModelForm):
    class Meta:
        model = EmailServiceConfig
        fields = "__all__"
        widgets = {
            # First positional arg is `attrs`, not `render_value` — pass attrs explicitly.
            "ses_secret_access_key": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
            "smtp_password": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }


@admin.register(EmailServiceConfig)
class EmailServiceConfigAdmin(ModelAdmin):
    form = EmailServiceConfigForm
    list_display = ("name", "status_badge", "provider_badge", "ses_from_email", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "ses_from_email", "smtp_host")
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config", "test_send_action"]
    actions_list = ["test_email_list", "test_sms_list"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("AWS SES (Primary)"),
            {
                "fields": (
                    "ses_access_key_id",
                    "ses_secret_access_key",
                    "ses_region",
                    "ses_from_email",
                    "ses_from_name",
                ),
                "description": "Leave Access Key blank to skip SES and use SMTP only.",
            },
        ),
        (
            _("SMTP (Fallback)"),
            {
                "fields": (
                    "smtp_host",
                    "smtp_port",
                    "smtp_use_tls",
                    "smtp_username",
                    "smtp_password",
                ),
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

    @display(description="Provider", label=True)
    def provider_badge(self, obj):
        if obj.ses_access_key_id:
            return "SES + SMTP", "info"
        return "SMTP only", "warning"

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = EmailServiceConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active email config.')
        return HttpResponseRedirect(reverse("admin:core_emailserviceconfig_change", args=[object_id]))

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
                name="core_emailserviceconfig_test_send",
            ),
            path(
                "test-email/",
                self.admin_site.admin_view(self.test_email_list_view),
                name="core_emailserviceconfig_test_email",
            ),
            path(
                "test-sms/",
                self.admin_site.admin_view(self.test_sms_list_view),
                name="core_emailserviceconfig_test_sms",
            ),
        ]
        return custom_urls + super().get_urls()

    @action(description="Send test email", url_path="test-send", icon="send")
    def test_send_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:core_emailserviceconfig_test_send", args=[object_id]))

    def test_send_view(self, request, object_id):
        obj = EmailServiceConfig.objects.get(pk=object_id)
        change_url = reverse("admin:core_emailserviceconfig_change", args=[object_id])

        if request.method == "POST":
            recipient = request.POST.get("recipient", "").strip()
            if not recipient:
                messages.error(request, "Please provide a recipient email address.")
                return HttpResponseRedirect(request.path)
            try:
                provider = _send_test_email(config=obj, recipient=recipient)
                messages.success(request, f"Test email sent to {recipient} via {provider}.")
            except Exception as exc:
                messages.error(request, f"Failed to send test email: {exc}")
            return HttpResponseRedirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Send Test Email — {obj.name}",
            "input_label": "Recipient email address",
            "input_type": "email",
            "input_placeholder": "admin@example.com",
            "input_help": f"A test email will be sent from {obj.source_address}.",
            "submit_label": "Send Test Email",
            "cancel_url": change_url,
        }
        return TemplateResponse(request, "admin/core/test_send_form.html", context)

    # -- List-level test actions ------------------------------------------------

    @action(description="Test Email", url_path="test-email-action", icon="mail")
    def test_email_list(self, request):
        return HttpResponseRedirect(reverse("admin:core_emailserviceconfig_test_email"))

    @action(description="Test SMS", url_path="test-sms-action", icon="sms")
    def test_sms_list(self, request):
        return HttpResponseRedirect(reverse("admin:core_emailserviceconfig_test_sms"))

    def test_email_list_view(self, request):
        config = EmailServiceConfig.load()
        changelist_url = reverse("admin:core_emailserviceconfig_changelist")

        if request.method == "POST":
            recipient = request.POST.get("recipient", "").strip()
            if not recipient:
                messages.error(request, "Please provide a recipient email address.")
                return HttpResponseRedirect(request.path)
            try:
                provider = _send_test_email(config=config, recipient=recipient)
                messages.success(request, f"Test email sent to {recipient} via {provider} (config: {config.name}).")
            except Exception as exc:
                messages.error(request, f"Failed to send test email: {exc}")
            return HttpResponseRedirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Send Test Email — {config.name}",
            "input_label": "Recipient email address",
            "input_type": "email",
            "input_placeholder": "admin@example.com",
            "input_help": f"A test email will be sent from {config.source_address} using the active config.",
            "submit_label": "Send Test Email",
            "cancel_url": changelist_url,
        }
        return TemplateResponse(request, "admin/core/test_send_form.html", context)

    def test_sms_list_view(self, request):
        config = SMSServiceConfig.load()
        changelist_url = reverse("admin:core_emailserviceconfig_changelist")

        if request.method == "POST":
            country_code = request.POST.get("country_code", "+1")
            recipient = request.POST.get("recipient", "").strip()
            if not recipient:
                messages.error(request, "Please provide a phone number.")
                return HttpResponseRedirect(request.path)
            full_number = _normalize_phone_number(country_code, recipient)
            try:
                result = _send_test_sms(config=config, phone_number=full_number)
                messages.success(request, f"Test SMS sent to {full_number}: {result} (config: {config.name}).")
            except Exception as exc:
                messages.error(request, f"Failed to send test SMS: {exc}")
            return HttpResponseRedirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Send Test SMS — {config.name}",
            "input_label": "Recipient phone number",
            "input_type": "tel",
            "input_placeholder": "2345678901",
            "input_help": "Select country code and enter the phone number.",
            "submit_label": "Send Test SMS",
            "cancel_url": changelist_url,
        }
        return TemplateResponse(request, "admin/core/test_send_form.html", context)


# ---------------------------------------------------------------------------
# Google Credentials
# ---------------------------------------------------------------------------


class GoogleCredentialConfigForm(forms.ModelForm):
    credentials_file = forms.FileField(
        required=False,
        label="Upload JSON Key File",
        help_text="Upload a Google service-account JSON key file. This will overwrite the current credentials.",
        widget=UnfoldAdminFileFieldWidget(attrs={"accept": ".json"}),
    )

    class Meta:
        model = GoogleCredentialConfig
        fields = "__all__"
        widgets = {
            "credentials_json": UnfoldAdminTextareaWidget(attrs={"rows": 12}),
        }

    def clean_credentials_file(self):
        f = self.cleaned_data.get("credentials_file")
        if f:
            import json

            try:
                data = json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise forms.ValidationError(f"Invalid JSON file: {exc}")
            if not isinstance(data, dict):
                raise forms.ValidationError("JSON file must contain an object, not a list or scalar.")
            return data
        return None

    def clean(self):
        cleaned = super().clean()
        file_data = cleaned.get("credentials_file")
        if file_data:
            cleaned["credentials_json"] = file_data
        return cleaned


@admin.register(GoogleCredentialConfig)
class GoogleCredentialConfigAdmin(ModelAdmin):
    form = GoogleCredentialConfigForm
    list_display = ("name", "status_badge", "project_id_display", "client_email_display", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("Service Account Credentials"),
            {
                "fields": ("credentials_file", "credentials_json"),
                "description": "Upload the JSON key file or paste its contents directly.",
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

    @display(description="Project ID")
    def project_id_display(self, obj):
        return obj.project_id or "—"

    @display(description="Client Email")
    def client_email_display(self, obj):
        return obj.client_email or "—"

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = GoogleCredentialConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active Google credential config.')
        return HttpResponseRedirect(reverse("admin:core_googlecredentialconfig_change", args=[object_id]))

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


# ---------------------------------------------------------------------------
# Gmail IMAP
# ---------------------------------------------------------------------------


class GmailImportConfigForm(forms.ModelForm):
    class Meta:
        model = GmailImportConfig
        fields = "__all__"
        widgets = {
            "gmail_password": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }


@admin.register(GmailImportConfig)
class GmailImportConfigAdmin(ModelAdmin):
    form = GmailImportConfigForm
    list_display = ("name", "status_badge", "imap_host", "gmail_username", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "gmail_username", "imap_host")
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("Gmail IMAP"),
            {
                "fields": ("imap_host", "gmail_username", "gmail_password"),
                "description": "Credentials used to read recent sent Gmail templates over IMAP.",
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
        obj = GmailImportConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active Gmail import config.')
        return HttpResponseRedirect(reverse("admin:core_gmailimportconfig_change", args=[object_id]))

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------


class SMSServiceConfigForm(forms.ModelForm):
    class Meta:
        model = SMSServiceConfig
        fields = "__all__"
        widgets = {
            "auth_token": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }


@admin.register(SMSServiceConfig)
class SMSServiceConfigAdmin(ModelAdmin):
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
            path(
                "test-email/",
                self.admin_site.admin_view(self.test_email_list_view),
                name="core_smsserviceconfig_test_email",
            ),
            path(
                "test-sms/",
                self.admin_site.admin_view(self.test_sms_list_view),
                name="core_smsserviceconfig_test_sms",
            ),
        ]
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

    # -- List-level test actions ------------------------------------------------

    @action(description="Test Email", url_path="test-email-action", icon="mail")
    def test_email_list(self, request):
        return HttpResponseRedirect(reverse("admin:core_smsserviceconfig_test_email"))

    @action(description="Test SMS", url_path="test-sms-action", icon="sms")
    def test_sms_list(self, request):
        return HttpResponseRedirect(reverse("admin:core_smsserviceconfig_test_sms"))

    def test_email_list_view(self, request):
        config = EmailServiceConfig.load()
        changelist_url = reverse("admin:core_smsserviceconfig_changelist")

        if request.method == "POST":
            recipient = request.POST.get("recipient", "").strip()
            if not recipient:
                messages.error(request, "Please provide a recipient email address.")
                return HttpResponseRedirect(request.path)
            try:
                provider = _send_test_email(config=config, recipient=recipient)
                messages.success(request, f"Test email sent to {recipient} via {provider} (config: {config.name}).")
            except Exception as exc:
                messages.error(request, f"Failed to send test email: {exc}")
            return HttpResponseRedirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Send Test Email — {config.name}",
            "input_label": "Recipient email address",
            "input_type": "email",
            "input_placeholder": "admin@example.com",
            "input_help": f"A test email will be sent from {config.source_address} using the active config.",
            "submit_label": "Send Test Email",
            "cancel_url": changelist_url,
        }
        return TemplateResponse(request, "admin/core/test_send_form.html", context)

    def test_sms_list_view(self, request):
        config = SMSServiceConfig.load()
        changelist_url = reverse("admin:core_smsserviceconfig_changelist")

        if request.method == "POST":
            country_code = request.POST.get("country_code", "+1")
            recipient = request.POST.get("recipient", "").strip()
            if not recipient:
                messages.error(request, "Please provide a phone number.")
                return HttpResponseRedirect(request.path)
            full_number = _normalize_phone_number(country_code, recipient)
            try:
                result = _send_test_sms(config=config, phone_number=full_number)
                messages.success(request, f"Test SMS sent to {full_number}: {result} (config: {config.name}).")
            except Exception as exc:
                messages.error(request, f"Failed to send test SMS: {exc}")
            return HttpResponseRedirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Send Test SMS — {config.name}",
            "input_label": "Recipient phone number",
            "input_type": "tel",
            "input_placeholder": "2345678901",
            "input_help": "Select country code and enter the phone number.",
            "submit_label": "Send Test SMS",
            "cancel_url": changelist_url,
        }
        return TemplateResponse(request, "admin/core/test_send_form.html", context)


# ---------------------------------------------------------------------------
# Helpers — test send
# ---------------------------------------------------------------------------


def _normalize_phone_number(country_code, recipient):
    """Build an E.164 number, stripping a leading '+' the admin may have pasted."""
    recipient = recipient.lstrip("+").strip()
    if not recipient:
        return ""
    return country_code + recipient


def _send_test_email(*, config, recipient):
    """Send a test email using the given EmailServiceConfig. Returns provider name."""
    subject = "Test Email — Innovate to Grow Admin"
    html_body = (
        "<h2>Test Email</h2>"
        "<p>This is a test email sent from the I2G admin panel.</p>"
        "<p>Your email service configuration is working correctly.</p>"
    )

    if config.ses_configured:
        try:
            import boto3

            client = boto3.client(
                "ses",
                region_name=config.ses_region,
                aws_access_key_id=config.ses_access_key_id,
                aws_secret_access_key=config.ses_secret_access_key,
            )
            client.send_email(
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Body": {"Html": {"Charset": "UTF-8", "Data": html_body}},
                    "Subject": {"Charset": "UTF-8", "Data": subject},
                },
                Source=config.source_address,
            )
            return "SES"
        except Exception:
            logger.exception("SES test send failed for %s", recipient)

    from django.core.mail import EmailMessage, get_connection

    connection = get_connection(
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.smtp_username,
        password=config.smtp_password,
        use_tls=config.smtp_use_tls,
        fail_silently=False,
    )
    msg = EmailMessage(
        subject=subject,
        body=html_body,
        from_email=config.source_address,
        to=[recipient],
        connection=connection,
    )
    msg.content_subtype = "html"
    msg.send()
    return "SMTP"


def _send_test_sms(*, config, phone_number):
    """Send a test SMS using the given SMSServiceConfig.

    If ``from_number`` is set, sends a plain text message via the Messages API.
    Otherwise falls back to a Twilio Verify code via the Verify API.
    Returns a short string describing what was sent.
    """
    import secrets

    if not config.account_sid or not config.auth_token:
        raise ValueError("Twilio credentials are not fully configured.")

    from twilio.rest import Client

    client = Client(config.account_sid, config.auth_token)

    if config.from_number:
        message = client.messages.create(
            to=phone_number,
            from_=config.from_number,
            body="This is a test message from the Innovate to Grow admin panel. Your SMS configuration is working correctly.",
        )
        warning = ""
        if not config.verify_sid:
            warning = " — Warning: Verify SID not set, login verification will not work"
        return f"message (SID: {message.sid}){warning}"

    if not config.verify_sid:
        raise ValueError("Either 'From Phone Number' or 'Verify Service SID' must be configured.")

    code = f"{secrets.randbelow(900000) + 100000}"
    client.verify.v2.services(config.verify_sid).verifications.create(to=phone_number, channel="sms", custom_code=code)
    return f"verification code [{code}]"
