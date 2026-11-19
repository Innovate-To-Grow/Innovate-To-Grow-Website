"""Health of the two sources of delivery evidence beyond bounce reports, for the Overview's delivery status card:

- the optional Microsoft Graph Message Trace sync (off unless the Graph config's ``message_trace_enabled`` is on; it
  needs the tenant-wide ``ExchangeMessageTrace.Read.All`` permission): its state row, its next sync and the latest
  "Check permissions" result of the active Graph config;
- the no-bounce inference, which needs no new permission: whether the bounce scans have read far enough past a send
  for an accepted email to show "No bounce received".

Nothing here contacts Microsoft: every value is what the sync's state row, the permission check's record and the
bounce scan's checkpoint already hold.
"""

from django.utils import timezone

from apps.core.admin.service_credentials.microsoft_graph.permissions import TRACE_SETUP_STEPS
from apps.core.models import (
    BackgroundJob,
    EmailDeliveryTraceState,
    EmailServiceConfig,
    MicrosoftGraphPermissionCheck,
    MicrosoftGraphProviderConfig,
)
from apps.core.services.email.bounces.recording.quiet import no_bounce_after_hours, quiet_until
from apps.core.services.email.graph.tracing import DELIVERY_TRACE_JOB_KIND, limits
from apps.core.services.email.inbound import format_interval
from apps.core.services.email.telemetry import text

Permission = EmailDeliveryTraceState.Permission
Trace = MicrosoftGraphPermissionCheck.TraceResult
# The card's state, and the bounce processing card's level whose icon and colour it borrows.
LEVELS = {
    "off": "inactive",
    "permission": "waiting",
    "waiting": "waiting",
    "throttled": "warning",
    "error": "error",
    "ok": "ok",
}
# The permission check's Message Trace result, in the card's words.
TRACE_RESULTS = {
    Trace.AVAILABLE: "available",
    Trace.NOT_GRANTED: "not granted",
    Trace.NO_SERVICE_PRINCIPAL: "service principal missing or still provisioning",
    Trace.NOT_CONSENTED: "permission not consented",
    Trace.THROTTLED: "throttled, try again later",
    Trace.ERROR: "error",
    Trace.NOT_CHECKED: "not checked (no token was issued)",
}


def _status(graph, state: EmailDeliveryTraceState | None, now) -> str:
    if not graph.message_trace_enabled:
        return "off"
    if not graph.is_configured:
        return "error"
    if state is None or state.last_run_finished_at is None:
        return "permission" if state is not None and state.permission == Permission.NOT_PERMITTED else "waiting"
    if state.permission == Permission.NOT_PERMITTED:
        return "permission"
    if (state.last_run_stats or {}).get("throttles") and state.next_run_after and state.next_run_after > now:
        return "throttled"
    failed_last = state.last_error_at and (state.last_success_at is None or state.last_error_at > state.last_success_at)
    if state.consecutive_failures or failed_last:
        return "error"
    return "ok"


def latest_permission_check(graph) -> dict | None:
    """The active Graph config's latest "Check permissions" run, as the card and the Mail Graph panel show it."""
    if graph._state.adding:
        return None
    check = graph.permission_checks.order_by("-created_at").first()
    if check is None:
        return None
    return {
        "check": check,
        "trace": TRACE_RESULTS.get(check.trace_result, check.get_trace_result_display()),
        "available": check.trace_result == Trace.AVAILABLE,
        "roles": list(check.granted_roles or ()),
        "roles_unreadable": check.token_ok and check.granted_roles is None,
    }


def delivery_trace(bounces: dict) -> dict:
    """The delivery status card: Message Trace's state and the no-bounce inference (``bounces`` is the bounce
    processing card's dict, whose scan coverage the inference relies on)."""
    now = timezone.now()
    graph = MicrosoftGraphProviderConfig.load()
    sender = text.address(EmailServiceConfig.load().from_email)
    state = EmailDeliveryTraceState.objects.filter(sender=sender).first() if sender else None
    status = _status(graph, state, now)
    next_job = (
        BackgroundJob.objects.filter(
            kind=DELIVERY_TRACE_JOB_KIND, status__in=[BackgroundJob.Status.PENDING, BackgroundJob.Status.RETRY]
        )
        .order_by("available_at")
        .values_list("available_at", flat=True)
        .first()
    )
    return {
        "enabled": bool(graph.message_trace_enabled),
        "status": status,
        "level": LEVELS[status],
        "problem": "Microsoft Graph is not configured." if status == "error" and not graph.is_configured else "",
        "sender": sender,
        "state": state,
        "stats": (state.last_run_stats if state else {}) or {},
        "running": bool(state and state.lease_until and state.lease_until >= now),
        "waiting_until": state.next_run_after
        if state and state.next_run_after and state.next_run_after > now
        else None,
        "next_sync_at": next_job,
        "every": format_interval(limits.interval_seconds()),
        "setup_steps": TRACE_SETUP_STEPS,
        "can_check_permissions": not graph._state.adding,
        "permission_check": latest_permission_check(graph),
        "inference": inference(bounces, sender),
    }


def inference(bounces: dict, sender: str) -> dict:
    """Whether "No bounce received" is being inferred: ``status`` is ``active`` (with the accepted times covered),
    ``off`` (bounce processing is not running), ``paused``, ``other_mailbox`` (the From address is not the mailbox
    the scans read, so its reports go elsewhere) or ``waiting`` (the scans have not read far enough yet)."""
    hours = no_bounce_after_hours()
    state = bounces.get("state")
    if not bounces.get("enabled") or not bounces.get("active"):
        return {"status": "off", "hours": hours}
    if sender != bounces.get("mailbox"):
        return {"status": "other_mailbox", "hours": hours}
    if state is not None and state.paused:
        return {"status": "paused", "hours": hours}
    until = quiet_until(state) if state is not None else None
    if until is None or until < state.scanned_since:
        return {"status": "waiting", "hours": hours}
    return {"status": "active", "hours": hours, "since": state.scanned_since, "until": until}
