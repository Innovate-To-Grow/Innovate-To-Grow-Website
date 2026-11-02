"""Notification Delivery test sends: one test email per email provider, and the test SMS.

``mail/settings/test-email/`` tests the provider email sends through now; ``mail/sending-method/<provider>/test-email/``
tests any of them, so a provider can be tried before email switches to it. A provider that switching to it would
refuse (``providers.provider_problem``) is never sent through.
"""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.core.admin.service_credentials.helpers import _normalize_phone_number, _send_test_email, _send_test_sms
from apps.core.models import AWSCredentialConfig, EmailServiceConfig

from .access import _require_mail_access
from .providers import Provider, as_provider, provider_or_404, provider_problem

TEST_FORM_TEMPLATE = "admin/core/test_send_form.html"


def get_test_send_urls():
    return [
        path(
            "mail/settings/test-email/",
            admin.site.admin_view(mail_settings_test_email_view),
            name="mail_settings_test_email",
        ),
        path(
            "mail/sending-method/<str:provider>/test-email/",
            admin.site.admin_view(mail_settings_test_email_provider_view),
            name="mail_settings_test_email_provider",
        ),
        path(
            "mail/settings/test-sms/",
            admin.site.admin_view(mail_settings_test_sms_view),
            name="mail_settings_test_sms",
        ),
    ]


def mail_settings_test_email_view(request):
    """A test email through the provider email is set to now (Notification Delivery's Send Test Email)."""
    _require_mail_access(request)
    return _test_email(request, EmailServiceConfig.load().provider, reverse("admin:mail_settings"))


def mail_settings_test_email_provider_view(request, provider):
    """A test email through any provider (Email Sending Method's Send test)."""
    _require_mail_access(request)
    return _test_email(request, provider_or_404(provider), reverse("admin:mail_sending_method"))


def _test_email(request, provider, settings_url):
    config = EmailServiceConfig.load()
    label = Provider(provider).label
    problem = provider_problem(config, provider)
    if request.method == "POST":
        recipient = request.POST.get("recipient", "").strip()
        error = _recipient_error(recipient)
        if error:
            messages.error(request, error)
            return HttpResponseRedirect(request.path)
        if problem:
            messages.error(request, f"Cannot send a test email through {label}: {problem}")
            return HttpResponseRedirect(settings_url)
        try:
            sent_via = _send_test_email(config=as_provider(config, provider), recipient=recipient)
            messages.success(request, f"Test email sent to {recipient} via {sent_via} (config: {config.name}).")
        except Exception as exc:
            messages.error(request, f"Failed to send test email: {exc}")
        return HttpResponseRedirect(settings_url)

    context = {
        **admin.site.each_context(request),
        "title": f"Send Test Email via {label} - Notification Delivery",
        "input_label": "Recipient email address",
        "input_type": "email",
        "input_placeholder": "admin@example.com",
        "input_help": f"A test email will be sent from {config.source_address} through {label}.",
        "submit_label": f"Send Test Email via {label}",
        "cancel_url": settings_url,
        "send_problem": problem,
        "method_links": _method_links(config, provider),
    }
    return TemplateResponse(request, TEST_FORM_TEMPLATE, context)


def _recipient_error(recipient: str) -> str:
    if not recipient:
        return "Please provide a recipient email address."
    try:
        validate_email(recipient)
    except ValidationError:
        return "Enter a valid recipient email address."
    return ""


def _method_links(config, selected: str) -> list[dict]:
    """The "Send through" choices on the test page: every provider, marked when it is in use or cannot send."""
    in_use = config.provider if config.is_active else ""
    return [
        {
            "label": label,
            "url": reverse("admin:mail_settings_test_email_provider", args=[provider]),
            "selected": provider == selected,
            "in_use": provider == in_use,
            "ready": not provider_problem(config, provider),
        }
        for provider, label in Provider.choices
    ]


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
    return TemplateResponse(request, TEST_FORM_TEMPLATE, context)
