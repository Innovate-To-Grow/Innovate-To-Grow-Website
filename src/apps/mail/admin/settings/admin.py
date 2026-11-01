"""Mail settings admin views."""

from django.contrib import admin, messages
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.core.admin.service_credentials.helpers import _normalize_phone_number, _send_test_email, _send_test_sms
from apps.core.admin.service_credentials.microsoft_graph_panel import certificate_panel
from apps.core.models import AWSCredentialConfig, EmailServiceConfig, MicrosoftGraphProviderConfig, SMTPProviderConfig
from apps.core.utils.access import user_can_access_app
from apps.mail.services.campaign.pacing import email_send_rate_line

from .forms import AwsDeliveryForm, EmailDeliveryForm, SMTPDeliveryForm


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
    graph_config = MicrosoftGraphProviderConfig.load()
    context = _notification_delivery_context(request, email_config, aws_config, smtp_config, graph_config)
    context["edit_url"] = reverse("admin:mail_settings_edit")
    return TemplateResponse(request, "admin/mail/settings.html", context)


def _save_delivery_forms(request, email_form, aws_form, provider_form) -> bool:
    """Save every delivery form together; False (with errors on the email form) if any is invalid.

    ``provider_form`` is the SMTP sub-form when SMTP is selected, or None. The Microsoft Graph config is never
    saved here: it is managed on its own admin page (Core app), and this page only selects it as the provider,
    which ``validate_activation`` allows only when it can send.
    """
    if not all([email_form.is_valid(), aws_form.is_valid(), provider_form is None or provider_form.is_valid()]):
        return False
    saved_forms = [form for form in (aws_form, provider_form, email_form) if form is not None]
    history = [_history_entry(form) for form in saved_forms]
    try:
        with transaction.atomic():
            aws_form.save()
            if provider_form is not None:
                provider_form.save()
            email_form.instance.validate_activation()
            email_form.save()
            _record_history(request, saved_forms, history)
    except ValidationError as exc:
        for field, errors in exc.message_dict.items():
            target = field if field in email_form.fields else None
            for error in errors:
                email_form.add_error(target, error)
        return False
    return True


def _history_entry(form):
    """``(action_flag, change_message)`` for a valid form about to be saved, or None when nothing changed."""
    if form.instance._state.adding:
        return ADDITION, [{"added": {}}]
    if not form.changed_data:
        return None
    return CHANGE, [{"changed": {"fields": [str(form.fields[name].label or name) for name in form.changed_data]}}]


def _record_history(request, forms, history) -> None:
    """Admin history for each saved row, as the model admins write it: who changed which fields (never values)."""
    for form, entry in zip(forms, history, strict=True):
        if entry is not None:
            action_flag, message = entry
            LogEntry.objects.log_actions(
                user_id=request.user.pk,
                queryset=[form.instance],
                action_flag=action_flag,
                change_message=message,
                single_object=True,
            )


_EDIT_FIELD_LISTS = {
    "aws_fields": ("aws_form", ("name", "is_active", "access_key_id", "secret_access_key", "default_region")),
    "sender_fields": ("email_form", ("name", "is_active", "provider", "from_name", "from_email")),
    "smtp_fields": (
        "smtp_form",
        ("name", "is_active", "host", "port", "username", "password", "use_tls", "use_ssl", "timeout"),
    ),
    "sms_fields": ("aws_form", ("sms_message_template",)),
}


def _delivery_forms(request, email_config, aws_config, smtp_config) -> dict:
    """Every delivery form, keyed for the template; only the selected provider's sub-form is bound to the data."""
    form_data = request.POST if request.method == "POST" else None
    selected_provider = request.POST.get("email-provider", email_config.provider)
    smtp_enabled = selected_provider == EmailServiceConfig.Provider.SMTP
    graph_enabled = selected_provider == EmailServiceConfig.Provider.GRAPH
    # An unused provider must not block edits or overwrite retained credentials.
    return {
        "email_form": EmailDeliveryForm(form_data, instance=email_config, prefix="email"),
        "aws_form": AwsDeliveryForm(form_data, instance=aws_config, prefix="aws"),
        "smtp_form": SMTPDeliveryForm(
            form_data if smtp_enabled else None, instance=smtp_config, prefix="smtp", enabled=smtp_enabled
        ),
        "smtp_enabled": smtp_enabled,
        "graph_enabled": graph_enabled,
    }


def mail_settings_edit_view(request):
    _require_mail_access(request)
    email_config = EmailServiceConfig.load()
    aws_config = AWSCredentialConfig.load()
    smtp_config = SMTPProviderConfig.load()
    graph_config = MicrosoftGraphProviderConfig.load()
    forms_by_name = _delivery_forms(request, email_config, aws_config, smtp_config)
    provider_form = forms_by_name["smtp_form"] if forms_by_name["smtp_enabled"] else None
    if request.method == "POST" and _save_delivery_forms(
        request, forms_by_name["email_form"], forms_by_name["aws_form"], provider_form
    ):
        messages.success(request, "Notification delivery settings saved.")
        return HttpResponseRedirect(reverse("admin:mail_settings"))
    context = _notification_delivery_context(request, email_config, aws_config, smtp_config, graph_config)
    context.update(forms_by_name)
    for key, (form_name, field_names) in _EDIT_FIELD_LISTS.items():
        context[key] = [forms_by_name[form_name][name] for name in field_names]
    return TemplateResponse(request, "admin/mail/settings_edit.html", context)


def _graph_context(request, graph_config) -> dict:
    """The active Graph config, read-only: it is managed on its own admin page, which needs the Core app."""
    saved = not graph_config._state.adding
    context = {
        "graph_saved": saved,
        "graph_scopes": list(graph_config.mailbox_scopes.all()) if saved else [],
        "graph_certificate_panel": certificate_panel(request, graph_config, actions=False),
        "graph_admin_url": "",
    }
    if user_can_access_app(request.user, "core"):
        context["graph_admin_url"] = (
            reverse("admin:core_microsoftgraphproviderconfig_change", args=[graph_config.pk])
            if saved
            else reverse("admin:core_microsoftgraphproviderconfig_add")
        )
    return context


def _notification_delivery_context(request, email_config, aws_config, smtp_config, graph_config):
    email_provider, email_provider_color = _email_provider_state(email_config, aws_config, smtp_config, graph_config)
    sms_provider, sms_provider_color = _sms_provider_state(aws_config)
    return {
        **admin.site.each_context(request),
        "title": "Notification Delivery",
        "config": email_config,
        "aws_config": aws_config,
        "smtp_config": smtp_config,
        "graph_config": graph_config,
        **_graph_context(request, graph_config),
        "email_status": "Active" if email_config.is_active else "Inactive",
        "email_send_rate": email_send_rate_line(),
        "aws_status": "Active" if aws_config.is_active else "Inactive",
        "masked_access_key": "Secrets Manager"
        if aws_config.credentials_secret_arn
        else _mask_key(aws_config.access_key_id),
        "secret_key_status": "Configured" if aws_config.is_configured else "Not configured",
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


def _email_provider_state(email_config, aws_config, smtp_config, graph_config):
    if email_config.provider == "smtp":
        if smtp_config.is_configured:
            return f"SMTP ({smtp_config.host}:{smtp_config.port})", "success"
        return "SMTP not configured", "warning"
    if email_config.provider == "graph":
        if graph_config.is_configured:
            return f"Microsoft Graph ({graph_config.mailbox or email_config.from_email})", "success"
        return "Microsoft Graph not configured", "warning"
    if aws_config.ses_configured:
        return f"Amazon Simple Email Service ({aws_config.region})", "success"
    return "Amazon Simple Email Service not configured", "warning"


def _sms_provider_state(aws_config):
    if aws_config.sns_configured:
        return f"Amazon Simple Notification Service ({aws_config.region})", "success"
    return "Amazon Simple Notification Service not configured", "warning"
