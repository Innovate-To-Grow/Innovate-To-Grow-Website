"""Broadcast Delivery → Email Sending Method: one card per email provider, and the switch between them.

Each card says whether the provider could send now and, if not, why: the reason is what ``validate_activation``
says when email would switch to it (so the Microsoft Graph and Gmail API go-live checks apply), checked on an unsaved
copy of the active config. The same check gates "Use for email" and that provider's test email, so neither can send
through a provider that switching to it would refuse.

The From address is shared by every provider, but Microsoft Graph can send only as a mailbox in its scope. When the
From address is outside it (the Google Workspace address AWS SES sends as, for example), switching to Graph also
moves the From address to Graph's configured sender mailbox (``switch_from_email``); the card says so first.
"""

from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.views.decorators.http import require_POST

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GmailApiProviderConfig,
    MicrosoftGraphProviderConfig,
    SMTPProviderConfig,
)
from apps.core.utils.access import user_can_access_app
from apps.core.utils.security import is_plain_address

from .access import _require_mail_access

Provider = EmailServiceConfig.Provider
NO_SENDER_CONFIG = "Save the Notification Delivery settings (sender name and From email) first."


def get_provider_urls():
    return [
        path(
            "mail/sending-method/",
            admin.site.admin_view(mail_sending_method_view),
            name="mail_sending_method",
        ),
        path(
            "mail/sending-method/<str:provider>/use/",
            admin.site.admin_view(mail_settings_use_provider_view),
            name="mail_settings_use_provider",
        ),
    ]


def provider_or_404(provider: str) -> str:
    if provider not in Provider.values:
        raise Http404("Unknown email provider.")
    return provider


def as_provider(config: EmailServiceConfig, provider: str) -> EmailServiceConfig:
    """An unsaved copy of *config*, active and set to *provider*: what email would be after switching to it."""
    return EmailServiceConfig(
        pk=config.pk,
        name=config.name,
        is_active=True,
        provider=provider,
        from_email=switch_from_email(config, provider),
        from_name=config.from_name,
    )


def switch_from_email(config: EmailServiceConfig, provider: str) -> str:
    """The From address email would send from after switching to *provider*.

    Every provider keeps the From address, except Microsoft Graph when Graph cannot send from it: Exchange sends only
    as mailboxes in the Graph scope, so that switch also moves the From address to the configured sender mailbox,
    when that mailbox is an email address Graph may send from. A provider email already uses keeps its From address,
    so a card for the method in use reports what email really sends with.
    """
    in_use = not config._state.adding and config.is_active and config.provider == provider
    if provider != Provider.GRAPH or in_use:
        return config.from_email
    graph = MicrosoftGraphProviderConfig.load()
    mailbox = graph.mailbox.strip()
    if graph.sending_ready(config.from_email) or not is_plain_address(mailbox) or not graph.sending_ready(mailbox):
        return config.from_email
    return mailbox


def provider_problem(config: EmailServiceConfig, provider: str) -> str:
    """Why email could not send through *provider* now, or "" when it could."""
    if config._state.adding:
        return NO_SENDER_CONFIG
    candidate = as_provider(config, provider)
    try:
        candidate.clean()
        candidate.validate_activation()
    except ValidationError as exc:
        reasons = exc.message_dict.get("provider", exc.messages) if hasattr(exc, "error_dict") else exc.messages
        return " ".join(reasons)
    return ""


def provider_cards(request, config, aws_config, smtp_config) -> list[dict]:
    """The Email sending method cards, in the provider choices' order."""
    details = _details(config, aws_config, smtp_config)
    in_use = config.provider if config.is_active else ""
    cards = []
    for provider, label in Provider.choices:
        problem = provider_problem(config, provider)
        from_email = "" if config._state.adding else switch_from_email(config, provider)
        cards.append(
            {
                "key": provider,
                "label": label,
                "detail": details[provider],
                "in_use": provider == in_use,
                "problem": problem,
                # Set only when switching to this provider also changes the From address.
                "switch_from_email": from_email if from_email != config.from_email else "",
                "test_url": reverse("admin:mail_settings_test_email_provider", args=[provider]),
                "use_url": reverse("admin:mail_settings_use_provider", args=[provider]),
                "configure_url": _configure_url(request, provider),
            }
        )
    return cards


def _details(config, aws_config, smtp_config) -> dict[str, str]:
    graph = MicrosoftGraphProviderConfig.load()
    return {
        Provider.SES: f"Region {aws_config.region}" if aws_config.ses_configured else "",
        Provider.SMTP: f"{smtp_config.host}:{smtp_config.port}" if smtp_config.is_configured else "",
        Provider.GRAPH: f"Mailbox {graph.sender_mailbox(config.from_email)}" if graph.is_configured else "",
        Provider.GMAIL: f"Sends as {config.from_email}" if GmailApiProviderConfig.load().is_configured else "",
    }


def _configure_url(request, provider: str) -> str:
    """Where this viewer sets the provider up, or "" when that needs access the viewer does not have."""
    if provider == Provider.SES:
        return reverse("admin:mail_settings_edit")
    if provider == Provider.SMTP:
        if user_can_access_app(request.user, "core"):
            return reverse("admin:core_smtpproviderconfig_changelist")
        return reverse("admin:mail_settings_edit")
    if provider == Provider.GRAPH:
        can_manage = user_can_access_app(request.user, "core")
        return reverse("admin:core_microsoftgraphproviderconfig_changelist") if can_manage else ""
    can_manage = user_can_access_app(request.user, "core")
    return reverse("admin:core_gmailapiproviderconfig_changelist") if can_manage else ""


def mail_sending_method_view(request):
    """Which API sends all site email, and a test through each (Mail app, as Notification Delivery)."""
    _require_mail_access(request)
    config = EmailServiceConfig.load()
    context = {
        **admin.site.each_context(request),
        "title": "Email Sending Method",
        "config": config,
        "sending_method": in_use_label(config),
        "provider_cards": provider_cards(request, config, AWSCredentialConfig.load(), SMTPProviderConfig.load()),
        "notification_delivery_url": reverse("admin:mail_settings"),
    }
    return TemplateResponse(request, "admin/mail/sending_method.html", context)


def in_use_label(config: EmailServiceConfig) -> str:
    """The method all email goes through now, or why none does."""
    if config._state.adding or not config.is_active:
        return "None (email sending is off)"
    return config.get_provider_display()


@require_POST
def mail_settings_use_provider_view(request, provider):
    """Switch email to *provider* (Mail app staff, as on the edit page), if switching to it is allowed."""
    _require_mail_access(request)
    provider = provider_or_404(provider)
    settings_url = reverse("admin:mail_sending_method")
    config = EmailServiceConfig.load()
    label = Provider(provider).label
    if not config._state.adding and config.provider == provider:
        messages.info(request, f"Email already sends through {label}.")
        return HttpResponseRedirect(settings_url)
    problem = provider_problem(config, provider)
    if problem:
        messages.error(request, f"Email cannot switch to {label}: {problem}")
        return HttpResponseRedirect(settings_url)
    previous, previous_from = config.get_provider_display(), config.from_email
    from_email = switch_from_email(config, provider)
    changed = ["Provider"] if from_email == previous_from else ["Provider", "From Email"]
    with transaction.atomic():
        config.provider = provider
        config.from_email = from_email
        config.validate_activation()
        config.save()
        LogEntry.objects.log_actions(
            user_id=request.user.pk,
            queryset=[config],
            action_flag=CHANGE,
            change_message=[{"changed": {"fields": changed}}],
            single_object=True,
        )
    done = f"Email now sends through {label} (was {previous})."
    if from_email != previous_from:
        done = f"{done} The From address is now {from_email} (was {previous_from})."
    messages.success(request, done)
    return HttpResponseRedirect(settings_url)
