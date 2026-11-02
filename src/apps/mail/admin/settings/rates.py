"""Mail → Delivery Rates: the Smart rate switch, the manual rate and the provider limits of every delivery channel.

Staff with the Mail app (the access Notification Delivery checks) edit all channels with one "Save delivery
rates". They can lower a documented limit, never raise it above its ``DELIVERY_RATES`` value. Every save and action
is a POST with CSRF and leaves an admin history line such as "sms_send: Smart rate on→off; manual 1→2".
"""

from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.db import transaction
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.views.decorators.http import require_GET, require_POST

from apps.core.models import AWSCredentialConfig, DeliveryRatePolicy, EmailServiceConfig
from apps.core.services.delivery_rates import (
    channel_info,
    refresh_discovery,
    reset_smart,
    resume,
    ses_identity,
    snapshot,
)

from .admin import _require_mail_access
from .rate_cards import (
    ACTIONS,
    build_card,
    card_groups,
    in_use_identities,
    placeholders,
    primary_states,
    status_payload,
)
from .rates_forms import MANUAL_RATE_NOTE, DeliveryRatePolicyForm

Channel = DeliveryRatePolicy.Channel
# How often the open page re-reads the live status (plan §2). A display refresh of data the limiter already holds:
# it sends nothing and changes no rate, so it is not one of the DELIVERY_RATES tunables.
STATUS_REFRESH_SECONDS = 15


def get_delivery_rate_urls():
    return [
        path("mail/settings/rates/", admin.site.admin_view(delivery_rates_view), name="mail_delivery_rates"),
        path(
            "mail/settings/rates/status/",
            admin.site.admin_view(delivery_rates_status_view),
            name="mail_delivery_rates_status",
        ),
        path(
            "mail/settings/rates/<str:channel>/<str:action>/",
            admin.site.admin_view(delivery_rates_action_view),
            name="mail_delivery_rates_action",
        ),
    ]


def _log(request, policy, message: str) -> None:
    LogEntry.objects.log_actions(
        user_id=request.user.pk, queryset=[policy], action_flag=CHANGE, change_message=message, single_object=True
    )


def _rates_url(channel: str = "") -> str:
    url = reverse("admin:mail_delivery_rates")
    return f"{url}#rate-card-{channel}" if channel else url


def _save(request, forms) -> int:
    """Save every changed policy together, with one history line each; return how many changed."""
    changed = [(form, form.change_summary()) for form in forms.values()]
    changed = [(form, summary) for form, summary in changed if summary]
    with transaction.atomic():
        for form, summary in changed:
            form.save()
            _log(request, form.instance, summary)
    return len(changed)


def delivery_rates_view(request):
    _require_mail_access(request)
    policies = {channel: DeliveryRatePolicy.for_channel(channel) for channel in Channel.values}
    in_use = in_use_identities()
    states = primary_states(in_use)
    data = request.POST if request.method == "POST" else None
    forms = {
        channel: DeliveryRatePolicyForm(
            data, instance=policy, prefix=channel, placeholders=placeholders(policy, states[channel])
        )
        for channel, policy in policies.items()
    }
    if data is not None:
        # Validate every form (no short-circuit), so each card shows its own errors.
        valid = [form.is_valid() for form in forms.values()]
        if all(valid):
            changed = _save(request, forms)
            if changed:
                messages.success(request, "Delivery rates saved.")
            else:
                messages.info(request, "No delivery rates changed.")
            return HttpResponseRedirect(_rates_url())
        messages.error(request, "The delivery rates were not saved. Please correct the errors below.")
    statuses = {status.channel: status for status in snapshot()}
    cards = {
        channel: build_card(forms[channel], statuses[channel], states[channel], in_use) for channel in Channel.values
    }
    context = {
        **admin.site.each_context(request),
        "title": "Delivery Rates",
        "manual_rate_note": MANUAL_RATE_NOTE,
        "status_url": reverse("admin:mail_delivery_rates_status"),
        "status_refresh_ms": STATUS_REFRESH_SECONDS * 1000,
        "all_cards": list(cards.values()),
        **card_groups(cards, EmailServiceConfig.load().provider),
    }
    return TemplateResponse(request, "admin/mail/settings_rates.html", context)


@require_GET
def delivery_rates_status_view(request):
    _require_mail_access(request)
    in_use = in_use_identities()
    # ``admin_view`` already marks the response never-cache.
    return JsonResponse({"channels": [status_payload(status, in_use) for status in snapshot()]})


def _discovery_identity(channel: str) -> str | None:
    """The identity a limit read is for: the AWS account in use for SES (whatever the email provider), the SMS
    number in use for SMS; None reads every identity the channel already knows."""
    if channel == Channel.SES_SEND:
        aws = AWSCredentialConfig.load()
        return ses_identity(aws.pk, aws.region) if aws.is_configured else None
    return in_use_identities().get(channel)


def _check(request, channel: str) -> None:
    read = refresh_discovery(channel, _discovery_identity(channel), force=True)
    if read:
        messages.success(
            request, "Provider limits read. The card shows what the provider reported, or why it could not."
        )
    else:
        messages.warning(request, "Nothing to read yet: this channel has no account or number in use.")


def _reset(request, channel: str) -> None:
    reset_smart(channel)
    messages.success(request, "Smart rate starts afresh with the next request. Pauses the provider asked for stay.")


def _resume(request, channel: str) -> None:
    resume(channel)
    messages.success(request, "Sending resumed: the pauses and stops of this channel are cleared.")


_RUNNERS = {"check": _check, "reset": _reset, "resume": _resume}


@require_POST
def delivery_rates_action_view(request, channel: str, action: str):
    _require_mail_access(request)
    if channel not in Channel.values or action not in _RUNNERS:
        raise Http404("No such delivery-rate action.")
    if action == "check" and not channel_info(channel).discovers:
        raise Http404("This provider reports no limits to read.")
    policy = DeliveryRatePolicy.for_channel(channel)
    _RUNNERS[action](request, channel)
    _log(request, policy, f"{channel}: {ACTIONS[action]}")
    return HttpResponseRedirect(_rates_url(channel))
