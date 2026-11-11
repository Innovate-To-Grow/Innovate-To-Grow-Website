"""Email Monitoring → Bounced addresses: the action POSTs.

Every action is two POSTs (with CSRF): ``step=confirm`` shows a confirmation page (what will happen, whether it can be
undone, the inputs, a typed confirmation where needed, and a fingerprint of the state it showed), then
``step=apply`` applies it, only when the guards still pass and nothing changed since (otherwise nothing is applied
and the page is shown again). Bulk applies one reversible address-level action to many rows the same way, row by row,
skipping each row that fails a guard with its reason; it never offers a contact or account change. Every view
requires the Mail app, and each action re-checks its own permissions.
"""

import uuid

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.mail.models import BouncedAddress, BouncedAddressAction
from apps.mail.services.email_monitoring.addresses import aggregate, audit
from apps.mail.services.email_monitoring.addresses.actions import (
    ActionRefused,
    StaleConfirmation,
    apply_action,
    deletion_summary,
)
from apps.mail.services.email_monitoring.addresses.guards import availability, fingerprint, load_target
from apps.mail.services.email_monitoring.addresses.replace import (
    NEW_ROLES,
    attest_allowed,
    secondary_taken,
)
from apps.mail.services.email_monitoring.addresses.specs import (
    QUICK_ACTIONS,
    SPECS,
    confirmation_required,
    confirmation_text,
)

from .views import TEMPLATES, _context, require_mail_access

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
    return TemplateResponse(request, f"{TEMPLATES}/address_confirm.html", context, status=status)


@require_POST
def address_action_view(request, pk, action):
    require_mail_access(request)
    if action not in SPECS:
        raise Http404("Unknown action.")
    row = get_object_or_404(BouncedAddress, pk=pk)
    values = _posted(request)
    if request.POST.get("step") != "apply":
        return _confirm_page(request, row, action, values)
    try:
        message = apply_action(request, row.pk, action, seen=request.POST.get("fingerprint", ""), values=values)
    except StaleConfirmation:
        messages.warning(request, STALE)
        return _confirm_page(request, row, action, values, status=409)
    except ActionRefused as exc:
        messages.error(request, str(exc))
        return _confirm_page(request, row, action, values, status=400)
    messages.success(request, message)
    # The address keeps its page and history, even after its contact email or account is deleted.
    return HttpResponseRedirect(_detail_url(row))


def _selected(request) -> list:
    ids = []
    for value in request.POST.getlist("ids")[: int(settings.EMAIL_MONITORING["address_bulk_max_rows"])]:
        try:
            ids.append(uuid.UUID(value))
        except (TypeError, ValueError):
            continue
    return list(BouncedAddress.objects.filter(pk__in=ids).order_by("address"))


def _bulk_rows(request, action: str, rows) -> list:
    entries = []
    for row in rows:
        target = load_target(row)
        verdict = availability(action, request, target)
        entries.append({"row": row, "target": target, "verdict": verdict, "fingerprint": fingerprint(target)})
    return entries


def _bulk_apply(request, action: str, rows, values: dict) -> tuple[list, list]:
    applied, skipped = [], []
    for row in rows:
        try:
            apply_action(request, row.pk, action, seen=request.POST.get(f"fp_{row.pk}", ""), values=values)
        except StaleConfirmation:
            skipped.append((row, "It changed since the confirmation page was shown."))
        except ActionRefused as exc:
            skipped.append((row, str(exc)))
        else:
            applied.append(row)
    return applied, skipped


@require_POST
def addresses_bulk_view(request):
    require_mail_access(request)
    action = request.POST.get("action", "")
    back = reverse("admin:mail_email_monitoring_addresses")
    if action not in QUICK_ACTIONS:
        messages.error(request, "Choose an action for the selected addresses.")
        return HttpResponseRedirect(back)
    rows = _selected(request)
    if not rows:
        messages.error(request, "Select at least one address.")
        return HttpResponseRedirect(back)
    values = {"note": str(request.POST.get("note") or "")[:500]}
    context = _context(request, f"{SPECS[action].label}: {len(rows)} addresses", None, "addresses")
    context.update(action=action, spec=SPECS[action], values=values, back_url=back)
    if request.POST.get("step") == "apply":
        applied, skipped = _bulk_apply(request, action, rows, values)
        context.update(applied=applied, skipped=skipped, done=True)
        if applied:
            messages.success(request, f"{SPECS[action].label}: {len(applied)} address(es) updated.")
        if skipped:
            messages.warning(request, f"{len(skipped)} address(es) skipped; see the reasons below.")
        return TemplateResponse(request, f"{TEMPLATES}/address_bulk.html", context)
    entries = _bulk_rows(request, action, rows)
    context.update(entries=entries, allowed=sum(1 for entry in entries if entry["verdict"].allowed))
    return TemplateResponse(request, f"{TEMPLATES}/address_bulk.html", context)


@require_POST
def addresses_rebuild_view(request):
    """Start counting again from the records still stored (review state and suppression are kept)."""
    require_mail_access(request)
    back = reverse("admin:mail_email_monitoring_addresses")
    if request.POST.get("step") != "apply":
        context = _context(request, "Rebuild bounced-address counts", None, "addresses")
        context.update(
            back_url=back,
            retention_days=settings.EMAIL_MONITORING["bounce_retention_days"],
            addresses=BouncedAddress.objects.count(),
        )
        return TemplateResponse(request, f"{TEMPLATES}/address_rebuild.html", context)
    aggregate.rebuild()
    counted = aggregate.run(max_rows=int(settings.EMAIL_MONITORING["address_page_rows"]))
    audit.record_rebuild(request, {"counted": counted["graph"] + counted["ses"]})
    messages.success(
        request,
        "The counts are being rebuilt from the stored records; the rest is counted as the page reloads and hourly.",
    )
    return HttpResponseRedirect(back)
