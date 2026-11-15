"""Email Monitoring → Bounce processing: the card's actions (scan now, pause, resume, and the forms in ``controls``)."""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.services.email.bounces import active_reader, run_now
from apps.core.services.email.bounces.scanning.state import is_paused, set_paused

from . import controls
from .views import require_mail_access


@require_POST
def bounce_processing_view(request):
    """Scan now, pause, resume, rescan since a time, or set the first-scan lookback of the Graph sending mailbox.

    A scan and a rescan need a mailbox the processor can read (the time a rescan sets is read by the next scan); the
    lookback, like pause and resume, needs only the mailbox."""
    require_mail_access(request)
    action = request.POST.get("action")
    reader, mailbox, problem = active_reader()
    target = reverse("admin:mail_email_monitoring")
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
