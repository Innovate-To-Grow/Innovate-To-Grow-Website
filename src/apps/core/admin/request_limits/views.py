"""Site Settings → Request Limits: every request-limit scope's priority tier, Smart limit switch and manual limit,
its limit now and why, its recent 429s, and which tiers Smart limiting is shedding.

Superusers and staff with the Core (System) app may view and edit; everyone else gets 403 (``admin_view`` only
checks ``is_staff``, so each view checks the app itself). All scopes are saved together with one "Save request
limits"; each changed row leaves an admin history line such as "auth-code-send: priority P0→P1; manual 10→20".
"""

from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.services.request_limits.overview import overview, policies
from apps.core.utils.access import user_can_access_app

from .cards import TIER_COPY, build_cards, status_payload, summary, tier_groups
from .forms import MANUAL_LIMIT_NOTE, RequestLimitPolicyForm

APP_LABEL = "core"
# How often the open page re-reads the live status (as Mail → Delivery Rates does). A display refresh: it changes no
# limit, so it is not one of the REQUEST_RATE_LIMITS tunables.
STATUS_REFRESH_SECONDS = 15


def get_request_limit_admin_urls(admin_site=None):
    site = admin_site or admin.site
    return [
        path("core/request-limits/", site.admin_view(request_limits_view), name="core_request_limits"),
        path(
            "core/request-limits/status/",
            site.admin_view(request_limits_status_view),
            name="core_request_limits_status",
        ),
    ]


def require_access(request) -> None:
    if not user_can_access_app(request.user, APP_LABEL):
        raise PermissionDenied("You do not have permission to manage request limits.")


def _log(request, policy, message: str) -> None:
    LogEntry.objects.log_actions(
        user_id=request.user.pk, queryset=[policy], action_flag=CHANGE, change_message=message, single_object=True
    )


def _save(request, forms) -> int:
    """Save every changed policy together, with one history line each; return how many changed."""
    changed = [(form, form.change_summary()) for form in forms.values()]
    changed = [(form, line) for form, line in changed if line]
    with transaction.atomic():
        for form, line in changed:
            form.save()
            _log(request, form.instance, line)
    return len(changed)


@require_http_methods(["GET", "POST"])
def request_limits_view(request):
    require_access(request)
    rows = policies()
    data = request.POST if request.method == "POST" else None
    forms = {scope: RequestLimitPolicyForm(data, instance=policy, prefix=scope) for scope, policy in rows.items()}
    if data is not None:
        # Validate every form (no short-circuit), so each card shows its own errors.
        valid = [form.is_valid() for form in forms.values()]
        if all(valid):
            if _save(request, forms):
                messages.success(request, "Request limits saved. Every web process applies them within seconds.")
            else:
                messages.info(request, "No request limits changed.")
            return HttpResponseRedirect(reverse("admin:core_request_limits"))
        messages.error(request, "The request limits were not saved. Please correct the errors below.")
        # Show the status of what is stored, not of the rejected input.
        rows = policies()
    status = overview(rows)
    cards = build_cards(forms, status)
    context = {
        **admin.site.each_context(request),
        "title": "Request Limits",
        "manual_limit_note": MANUAL_LIMIT_NOTE,
        "status_url": reverse("admin:core_request_limits_status"),
        "status_refresh_ms": STATUS_REFRESH_SECONDS * 1000,
        "summary": summary(status),
        "tier_copy": TIER_COPY,
        "groups": tier_groups(cards, status),
        "history_url": reverse("admin:admin_logentry_changelist"),
    }
    return TemplateResponse(request, "admin/core/request_limits.html", context)


@require_GET
def request_limits_status_view(request):
    require_access(request)
    rows = policies()
    # ``admin_view`` already marks the response never-cache.
    return JsonResponse(status_payload(overview(rows), {scope: row.label for scope, row in rows.items()}))
