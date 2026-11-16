"""Email Monitoring → Bounced addresses: the confirmation step every address action POSTs first."""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.mail.models import BouncedAddressAction
from apps.mail.services.email_monitoring.addresses.actions import (
    deletion_summary,
)
from apps.mail.services.email_monitoring.addresses.actions.guards import availability
from apps.mail.services.email_monitoring.addresses.actions.replace import (
    NEW_ROLES,
    attest_allowed,
    secondary_taken,
)
from apps.mail.services.email_monitoring.addresses.actions.specs import (
    SPECS,
    confirmation_required,
    confirmation_text,
)
from apps.mail.services.email_monitoring.addresses.actions.targets import fingerprint, load_target

from .views import TEMPLATES, _context

Action = BouncedAddressAction.Action


POSTED_FIELDS = (
    "note",
    "confirm",
    "new_primary",
    "new_address",
    "new_role",
    "attest_verified",
    "subscribe",
    "old_address",
)


STALE = (
    "The address, its contact emails or the member changed since the confirmation page was shown, so nothing was "
    "changed. Review the current state and confirm again."
)


def _posted(request) -> dict:
    return {name: str(request.POST.get(name) or "")[:500] for name in POSTED_FIELDS}


def _detail_url(row) -> str:
    return reverse("admin:mail_email_monitoring_address", args=[row.pk])


def _confirm_context(request, row, action: str, values: dict) -> dict:
    target = load_target(row)
    spec = SPECS[action]
    member = target.member
    context = _context(request, f"{spec.label} - {row.address}", None, "addresses")
    context.update(
        row=row,
        target=target,
        action=action,
        spec=spec,
        values=values,
        fingerprint=fingerprint(target),
        verdict=availability(action, request, target),
        typed=confirmation_text(action, target) if confirmation_required() else "",
        other_verified=target.other_verified(),
        cancel_url=_detail_url(row),
    )
    if action == Action.REPLACE and member is not None:
        context.update(
            new_roles=NEW_ROLES,
            attest_allowed=attest_allowed(request, member),
            secondary_taken=secondary_taken(target, deleting_old=False),
            old_typed=target.contact.email_address if confirmation_required() else "",
            subscribe_default=target.contact.subscribe,
        )
    if action == Action.DELETE_ACCOUNT and member is not None and context["verdict"].allowed:
        context["deletion"] = deletion_summary(request, member)
    return context


def _confirm_page(request, row, action: str, values: dict, *, status: int = 200):
    context = _confirm_context(request, row, action, values)
    if not context["verdict"].allowed:
        messages.error(request, context["verdict"].reason)
        return HttpResponseRedirect(_detail_url(row))
    return TemplateResponse(request, f"{TEMPLATES}/addresses/address_confirm.html", context, status=status)
