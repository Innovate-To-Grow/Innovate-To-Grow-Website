"""Mail settings admin views."""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from apps.core.admin.service_credentials.helpers import _normalize_phone_number, _send_test_email, _send_test_sms
from apps.core.models import AWSCredentialConfig, EmailServiceConfig, SMTPProviderConfig
from apps.core.utils.access import user_can_access_app


class EmailDeliveryForm(forms.ModelForm):
    class Meta:
        model = EmailServiceConfig
        fields = (
            "name",
            "is_active",
            "provider",
            "from_name",
            "from_email",
            "max_send_rate",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_admin_widget_classes(self)


class AwsDeliveryForm(forms.ModelForm):
    class Meta:
        model = AWSCredentialConfig
        fields = (
            "name",
            "is_active",
            "access_key_id",
            "secret_access_key",
            "default_region",
            "sms_message_template",
        )
        widgets = {
            "secret_access_key": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_admin_widget_classes(self)


class SMTPDeliveryForm(forms.ModelForm):
    class Meta:
        model = SMTPProviderConfig
        fields = ("name", "is_active", "host", "port", "username", "password", "use_tls", "use_ssl", "timeout")
        widgets = {"password": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=False)}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].required = False
        self.fields["password"].help_text = "Leave blank to keep the existing password."
        _apply_admin_widget_classes(self)

    def clean_password(self):
        return self.cleaned_data["password"] or self.instance.password


def _apply_admin_widget_classes(form):
    input_class = "w-full rounded-md border border-base-300 px-3 py-2 text-sm"
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.setdefault("class", "rounded border-base-300")
            continue
        existing = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = f"{existing} {input_class}".strip()


def get_mail_settings_urls():
    return [
        path("mail/settings/", admin.site.admin_view(mail_settings_view), name="mail_settings"),
        path("mail/settings/edit/", admin.site.admin_view(mail_settings_edit_view), name="mail_settings_edit"),
        path(
            "mail/settings/test-email/",
            admin.site.admin_view(mail_settings_test_email_view),
            name="mail_settings_test_email",
        ),
        path(
            "mail/settings/test-sms/",
            admin.site.admin_view(mail_settings_test_sms_view),
            name="mail_settings_test_sms",
        ),
    ]


def _require_mail_access(request):
    # ``admin_view`` only enforces is_staff, so these custom URLs must re-check
    # per-app access themselves — Django never runs the per-app model permissions
    # for a standalone admin view.
    if not user_can_access_app(request.user, "mail"):
        raise PermissionDenied("You do not have permission to access mail settings.")


def mail_settings_view(request):
    _require_mail_access(request)
    if request.GET.get("refresh"):
        from apps.core.services.aws.sms import clear_origination_number_cache

        clear_origination_number_cache()
    email_config = EmailServiceConfig.load()
    aws_config = AWSCredentialConfig.load()
    smtp_config = SMTPProviderConfig.load()
    context = _notification_delivery_context(request, email_config, aws_config, smtp_config)
    context["edit_url"] = reverse("admin:mail_settings_edit")
    return TemplateResponse(request, "admin/mail/settings.html", context)


def mail_settings_edit_view(request):
    _require_mail_access(request)
    email_config = EmailServiceConfig.load()
    aws_config = AWSCredentialConfig.load()
    smtp_config = SMTPProviderConfig.load()
    if request.method == "POST":
        selected_provider = request.POST.get("email-provider", email_config.provider)
        email_form = EmailDeliveryForm(request.POST, instance=email_config, prefix="email")
        aws_form = AwsDeliveryForm(request.POST, instance=aws_config, prefix="aws")
        smtp_form = SMTPDeliveryForm(request.POST, instance=smtp_config, prefix="smtp")
        if selected_provider != EmailServiceConfig.Provider.SMTP and smtp_config._state.adding:
            for name in ("host", "port", "timeout"):
                smtp_form.fields[name].required = False
        if email_form.is_valid() and aws_form.is_valid() and smtp_form.is_valid():
            try:
                with transaction.atomic():
                    aws_form.save()
                    if smtp_form.cleaned_data.get("host") or not smtp_config._state.adding:
                        smtp_form.save()
                    email_form.instance.validate_activation()
                    email_form.save()
            except ValidationError as exc:
                for field, errors in exc.message_dict.items():
                    target = field if field in email_form.fields else None
                    for error in errors:
                        email_form.add_error(target, error)
            else:
                messages.success(request, "Notification delivery settings saved.")
                return HttpResponseRedirect(reverse("admin:mail_settings"))
    else:
        email_form = EmailDeliveryForm(instance=email_config, prefix="email")
        aws_form = AwsDeliveryForm(instance=aws_config, prefix="aws")
        smtp_form = SMTPDeliveryForm(instance=smtp_config, prefix="smtp")

    context = _notification_delivery_context(request, email_config, aws_config, smtp_config)
    context.update(
        {
            "email_form": email_form,
            "aws_form": aws_form,
            "smtp_form": smtp_form,
            "aws_fields": [
                aws_form[name] for name in ("name", "is_active", "access_key_id", "secret_access_key", "default_region")
            ],
            "sender_fields": [
                email_form[name]
                for name in ("name", "is_active", "provider", "from_name", "from_email", "max_send_rate")
            ],
            "smtp_fields": [
                smtp_form[name]
                for name in (
                    "name",
                    "is_active",
                    "host",
                    "port",
                    "username",
                    "password",
                    "use_tls",
                    "use_ssl",
                    "timeout",
                )
            ],
            "sms_fields": [aws_form[name] for name in ("sms_message_template",)],
        }
    )
    return TemplateResponse(request, "admin/mail/settings_edit.html", context)


def _notification_delivery_context(request, email_config, aws_config, smtp_config):
    email_provider, email_provider_color = _email_provider_state(email_config, aws_config, smtp_config)
    sms_provider, sms_provider_color = _sms_provider_state(aws_config)
    return {
        **admin.site.each_context(request),
        "title": "Notification Delivery",
        "config": email_config,
        "aws_config": aws_config,
        "smtp_config": smtp_config,
        "email_status": "Active" if email_config.is_active else "Inactive",
        "aws_status": "Active" if aws_config.is_active else "Inactive",
        "masked_access_key": _mask_key(aws_config.access_key_id),
        "secret_key_status": "Configured" if aws_config.secret_access_key else "Not configured",
        "resolved_sms_number": aws_config.resolved_sms_from_number(),
        "sms_number_is_override": bool(aws_config.sms_from_number),
        "sms_template_display": aws_config.sms_message_template or "Default OTP message",
        "email_provider": email_provider,
        "email_provider_color": email_provider_color,
        "sms_provider": sms_provider,
        "sms_provider_color": sms_provider_color,
        "test_email_url": reverse("admin:mail_settings_test_email"),
        "test_sms_url": reverse("admin:mail_settings_test_sms"),
    }


def _mask_key(value):
    if not value:
        return "Not configured"
    return f"...{value[-4:]}"


def mail_settings_test_email_view(request):
    _require_mail_access(request)
    config = EmailServiceConfig.load()
    settings_url = reverse("admin:mail_settings")

    if request.method == "POST":
        recipient = request.POST.get("recipient", "").strip()
        if not recipient:
            messages.error(request, "Please provide a recipient email address.")
            return HttpResponseRedirect(reverse("admin:mail_settings_test_email"))
        try:
            provider = _send_test_email(config=config, recipient=recipient)
            messages.success(request, f"Test email sent to {recipient} via {provider} (config: {config.name}).")
        except Exception as exc:
            messages.error(request, f"Failed to send test email: {exc}")
        return HttpResponseRedirect(settings_url)

    context = {
        **admin.site.each_context(request),
        "title": "Send Test Email - Notification Delivery",
        "input_label": "Recipient email address",
        "input_type": "email",
        "input_placeholder": "admin@example.com",
        "input_help": f"A test email will be sent from {config.source_address} through {config.get_provider_display()}.",
        "submit_label": "Send Test Email",
        "cancel_url": settings_url,
    }
    return TemplateResponse(request, "admin/core/test_send_form.html", context)


def mail_settings_test_sms_view(request):
    _require_mail_access(request)
    config = AWSCredentialConfig.load()
    settings_url = reverse("admin:mail_settings")

    if request.method == "POST":
        country_code = request.POST.get("country_code", "+1")
        recipient = request.POST.get("recipient", "").strip()
        if not recipient:
            messages.error(request, "Please provide a phone number.")
            return HttpResponseRedirect(reverse("admin:mail_settings_test_sms"))
        full_number = _normalize_phone_number(country_code, recipient)
        try:
            result = _send_test_sms(phone_number=full_number)
            messages.success(request, f"Test SMS sent to {full_number}: {result} (AWS config: {config.name}).")
        except Exception as exc:
            messages.error(request, f"Failed to send test SMS: {exc}")
        return HttpResponseRedirect(settings_url)

    context = {
        **admin.site.each_context(request),
        "title": "Send Test SMS - Notification Delivery",
        "input_label": "Recipient phone number",
        "input_type": "tel",
        "input_placeholder": "2345678901",
        "input_help": (
            "Select country code and enter the phone number. The message will be sent through AWS End User Messaging."
        ),
        "submit_label": "Send Test SMS",
        "cancel_url": settings_url,
    }
    return TemplateResponse(request, "admin/core/test_send_form.html", context)


def _email_provider_state(email_config, aws_config, smtp_config):
    if email_config.provider == "smtp":
        if smtp_config.is_configured:
            return f"SMTP ({smtp_config.host}:{smtp_config.port})", "success"
        return "SMTP not configured", "warning"
    if aws_config.ses_configured:
        return f"Amazon Simple Email Service ({aws_config.region})", "success"
    return "Amazon Simple Email Service not configured", "warning"


def _sms_provider_state(aws_config):
    if aws_config.sns_configured:
        return f"Amazon Simple Notification Service ({aws_config.region})", "success"
    return "Amazon Simple Notification Service not configured", "warning"
