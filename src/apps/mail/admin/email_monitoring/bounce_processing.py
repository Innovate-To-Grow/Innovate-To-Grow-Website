"""Email Monitoring → the Overview's cards' actions: bounce processing (scan now, pause, resume, and the forms in
``controls``) and delivery status (sync the Message Trace now; check the Graph permissions, read-only).

"Check permissions" is the Core Graph config page's check (``access_check.permissions.run_and_record``) with its
30-second cooldown per config: one fresh token and its roles, and at most one read-only trace request. It sends no
mail and never records go-live evidence.
"""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.admin.service_credentials.microsoft_graph.permissions import COOLING_DOWN, cooldown_seconds
from apps.core.models import EmailDeliveryTraceState, EmailServiceConfig, MicrosoftGraphProviderConfig
from apps.core.services.email.bounces import active_reader, run_now
from apps.core.services.email.bounces.scanning.state import is_paused, set_paused
from apps.core.services.email.graph import tracing
from apps.core.services.email.graph.access_check import permissions
from apps.core.services.email.graph.tracing.sync import enabled as trace_enabled
from apps.core.services.email.telemetry import text

from . import controls
from .views import require_mail_access


@require_POST
def bounce_processing_view(request):
    """Scan now, pause, resume, rescan since a time, or set the first-scan lookback of the Graph sending mailbox; or,
    on the delivery status card, sync the Message Trace now (``trace``) or check the Graph permissions
    (``permissions``).

    A scan and a rescan need a mailbox the processor can read (the time a rescan sets is read by the next scan); the
    lookback, like pause and resume, needs only the mailbox."""
    require_mail_access(request)
    action = request.POST.get("action")
    target = reverse("admin:mail_email_monitoring")
    if action == "trace":
        _sync_trace_now(request)
        return HttpResponseRedirect(target)
    if action == "permissions":
        _check_permissions(request)
        return HttpResponseRedirect(target)
    reader, mailbox, problem = active_reader()
    if action == "scan" and reader is not None:
        _scan_now(request, mailbox)
    elif action in ("pause", "resume") and mailbox:
        set_paused(mailbox, action == "pause")
        verb = "paused" if action == "pause" else "resumed"
        messages.success(request, f"Bounce processing for {mailbox} {verb}.")
    elif action == "rescan" and reader is not None:
        controls.rescan(request, mailbox)
    elif action == "lookback" and mailbox:
        controls.lookback(request, mailbox)
    else:
        messages.error(request, problem or "Unknown bounce processing action.")
    return HttpResponseRedirect(target)


def _scan_now(request, mailbox: str) -> None:
    """Queue a scan at once, unless processing is paused (the scan would read nothing: resume first) or switched off.
    The card offers no working button then; this answers a stale page or a second tab the same way."""
    if is_paused(mailbox):
        messages.warning(request, f"Bounce processing for {mailbox} is paused: resume it to scan.")
    elif run_now():
        messages.success(request, "A bounce scan was queued; the background worker runs it within a minute.")
    else:
        messages.warning(request, "Bounce processing is turned off (EMAIL_BOUNCE_PROCESSING_ENABLED).")


def _sync_trace_now(request) -> None:
    """Pull the waiting Message Trace sync forward (``tracing.run_now``): never a second one, and the sender's
    backoff (a throttle, or a permission Microsoft has not granted) still holds."""
    if not trace_enabled():
        messages.warning(
            request,
            "Message Trace delivery status is off: it is switched on on the Microsoft Graph configuration (Core app) "
            "once its permission is granted.",
        )
        return
    if not tracing.run_now():
        messages.info(request, "A delivery status sync is running now; its results show here when it finishes.")
        return
    sender = text.address(EmailServiceConfig.load().from_email)
    state = EmailDeliveryTraceState.objects.filter(sender=sender).first() if sender else None
    if state is not None and state.next_run_after and state.next_run_after > timezone.now():
        when = timezone.localtime(state.next_run_after).strftime("%H:%M")
        messages.warning(
            request,
            f"A delivery status sync was queued, but it waits until {when}: Microsoft asked to wait, or the Message "
            "Trace permission is not granted yet (Check permissions ends that wait once it is).",
        )
        return
    messages.success(request, "A delivery status sync was queued; the background worker runs it within a minute.")


def _check_permissions(request) -> None:
    graph = MicrosoftGraphProviderConfig.load()
    if graph._state.adding:
        messages.error(request, "Microsoft Graph is not configured, so there are no permissions to check.")
        return
    wait = cooldown_seconds(graph)
    if wait:
        messages.warning(request, COOLING_DOWN.format(seconds=wait))
        return
    report, _check = permissions.run_and_record(graph, checked_by=request.user)
    level = messages.SUCCESS if report.token_ok and not report.warning else messages.WARNING
    if not report.token_ok:
        level = messages.ERROR
    messages.add_message(request, level, " ".join(filter(None, (report.summary(), report.warning))))
