"""Mail settings admin views."""

from django.contrib import admin, messages
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    MicrosoftGraphProviderConfig,
    SMTPProviderConfig,
)
from apps.mail.admin.settings.admin.context import _notification_delivery_context

from ..providers import get_provider_urls, in_use_label
from .access import _require_mail_access
from .forms import AwsDeliveryForm, EmailDeliveryForm, SMTPDeliveryForm
from .test_send import get_test_send_urls


def get_mail_settings_urls():
    return [
        path("mail/settings/", admin.site.admin_view(mail_settings_view), name="mail_settings"),
        path("mail/settings/edit/", admin.site.admin_view(mail_settings_edit_view), name="mail_settings_edit"),
        *get_test_send_urls(),
        *get_provider_urls(),
    ]


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
    context["sending_method"] = in_use_label(email_config)
    context["sending_method_url"] = reverse("admin:mail_sending_method")
    return TemplateResponse(request, "admin/mail/settings/notification_delivery/settings.html", context)


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
    gmail_enabled = selected_provider == EmailServiceConfig.Provider.GMAIL
    # An unused provider must not block edits or overwrite retained credentials.
    return {
        "email_form": EmailDeliveryForm(form_data, instance=email_config, prefix="email"),
        "aws_form": AwsDeliveryForm(form_data, instance=aws_config, prefix="aws"),
        "smtp_form": SMTPDeliveryForm(
            form_data if smtp_enabled else None, instance=smtp_config, prefix="smtp", enabled=smtp_enabled
        ),
        "smtp_enabled": smtp_enabled,
        "graph_enabled": graph_enabled,
        "gmail_enabled": gmail_enabled,
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
    return TemplateResponse(request, "admin/mail/settings/notification_delivery/settings_edit.html", context)
