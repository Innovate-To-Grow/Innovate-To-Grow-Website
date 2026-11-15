"""Helpdesk → Settings → Intake: the controls of the helpdesk's own Inbox scan, on the card above the settings form.

Scan now, Pause / Resume, "Rescan since" and the first-scan lookback change only the intake's state row (through
``services.intake.state``, which applies the bounds of ``inbox_max_lookback_days``, the lease rule and the audit
trail: an admin history line and a log line), never bounce processing's. Only Scan now starts a scan; the others take
effect at the next scheduled scan. Each control is a POST with CSRF and needs the Helpdesk grant (``admin_view`` only
requires a staff login); every message names what changed, or why nothing did.
"""

from django import forms
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import formats, timezone
from django.views.decorators.http import require_POST

from apps.core.services.email.bounces import active_reader
from apps.core.services.email.inbound import format_interval

from ..services.ingest import jobs as ingest_jobs
from ..services.intake import jobs as intake_jobs
from ..services.intake import state as intake_state
from .views import require_helpdesk_access

# How a time is shown in a message: the site's time zone, to the minute, with the zone's abbreviation.
WHEN = "M j, Y, H:i T"
NOT_AFFECTED = "Bounce processing (Email Monitoring) is not affected."


def when(value) -> str:
    return formats.date_format(timezone.localtime(value), WHEN) if value else "none"


class RescanForm(forms.Form):
    # A ``datetime-local`` value is read in the site's time zone; a time that does not exist or occurs twice there
    # (a daylight-saving change) is refused by the field.
    since = forms.DateTimeField(
        error_messages={
            "required": "enter the date and time to rescan from.",
            "invalid": "enter a valid date and time.",
        }
    )


class LookbackForm(forms.Form):
    lookback_hours = forms.IntegerField(required=False, error_messages={"invalid": "enter a whole number of hours."})

    def clean_lookback_hours(self):
        hours = self.cleaned_data["lookback_hours"]
        low, high = intake_state.lookback_bounds()
        if hours is not None and not low <= hours <= high:
            raise forms.ValidationError(
                f"enter {low:,} to {high:,} hours, or leave it empty for the default "
                f"({intake_state.default_lookback_hours():,} hours)."
            )
        return hours


def _hours(hours: int) -> str:
    return f"{hours:,} hour{'' if hours == 1 else 's'}"


def _first_error(form: forms.Form) -> str:
    return next(iter(form.errors.values()))[0]


@require_POST
def intake_view(request):
    """Scan now, pause, resume, rescan since a time, or set the first-scan lookback of the intake.

    A scan and a rescan need a mailbox the intake can read (the time a rescan sets is read by the next scan); the
    lookback, like pause and resume, needs only the mailbox."""
    require_helpdesk_access(request)
    action = request.POST.get("action")
    reader, mailbox, problem = active_reader()
    if action == "scan" and reader is not None:
        _scan_now(request, mailbox)
    elif action in ("pause", "resume") and mailbox:
        _pause(request, mailbox, paused=action == "pause")
    elif action == "rescan" and reader is not None:
        _rescan(request, mailbox)
    elif action == "lookback" and mailbox:
        _lookback(request, mailbox)
    else:
        messages.error(request, problem or "Unknown intake action.")
    return HttpResponseRedirect(f"{reverse('admin:helpdesk_helpdesksettings_changelist')}#helpdesk-intake")


def _scan_now(request, mailbox: str) -> None:
    if intake_state.is_paused(mailbox):
        messages.warning(request, f"The intake of {mailbox} is paused: resume it to scan.")
    elif intake_jobs.run_now():
        messages.success(
            request, f"An intake scan of {mailbox} was queued; the background worker runs it within a minute."
        )
    else:
        messages.warning(request, "The helpdesk is switched off (Enabled, below), so no scan was queued.")


def _pause(request, mailbox: str, *, paused: bool) -> None:
    changed = intake_state.set_paused(mailbox, paused, actor=request.user)
    if not changed:
        current = "paused" if paused else "running"
        messages.info(request, f"The intake of {mailbox} is already {current}; nothing changed.")
    elif paused:
        messages.success(
            request,
            f"Intake of {mailbox} paused: the helpdesk neither lists the Inbox nor imports mail until it is resumed; "
            f"its checkpoint stays, so nothing is missed. {NOT_AFFECTED}",
        )
    else:
        ingest_jobs.ensure_scheduled()
        every = format_interval(intake_jobs.interval_seconds())
        messages.success(
            request,
            f"Intake of {mailbox} resumed: the next scan (within {every}) continues from the checkpoint, and mail "
            f"waiting in the queue is imported. {NOT_AFFECTED}",
        )


def _rescan(request, mailbox: str) -> None:
    """Move the intake's checkpoint back to the posted time (``action=rescan``)."""
    form = RescanForm(request.POST)
    if not form.is_valid():
        messages.error(request, f"The intake checkpoint was not moved: {_first_error(form)}")
        return
    result = intake_state.rescan_since(mailbox, form.cleaned_data["since"], actor=request.user)
    level, text = _rescan_message(mailbox, result)
    messages.add_message(request, level, text)


def _then(paused: bool) -> str:
    if not intake_jobs.enabled():
        return "once the helpdesk is switched on (Enabled, below)"
    if paused:
        return "once the intake is resumed (it is paused)"
    every = format_interval(intake_jobs.interval_seconds())
    return f"at the next scheduled scan (within {every}), or sooner with Scan now"


def _rescan_message(mailbox: str, result: intake_state.Rescan) -> tuple[int, str]:
    since = when(result.since)
    if result.status == "moved":
        moved = (
            f"the intake checkpoint moved back from {when(result.previous)} to {since}"
            if result.previous
            else f"its first scan reads mail received since {since}"
        )
        return messages.SUCCESS, (
            f"Rescan set for {mailbox}: {moved}. The helpdesk lists the Inbox again from that time "
            f"{_then(result.paused)}; messages it already recorded are skipped, so no ticket is made twice. "
            f"{NOT_AFFECTED}"
        )
    if result.status == "not_earlier":
        return messages.INFO, (
            f"Nothing changed: the intake checkpoint ({when(result.previous)}) is already at or before {since}, so "
            "the next scan reads from there anyway."
        )
    if result.status == "running":
        return messages.WARNING, (
            f"An intake scan of {mailbox} is running, so the checkpoint was not moved (the scan would save its own "
            f"over it). Try again in a minute: the scan holds the mailbox until {when(result.lease_until)} at the "
            "latest."
        )
    if result.status == "future":
        return messages.ERROR, f"The intake checkpoint was not moved: {since} is in the future."
    return messages.ERROR, (
        f"The intake checkpoint was not moved: {since} is more than {intake_state.max_lookback_days()} days ago. "
        f"Choose {when(result.earliest)} or later."
    )


def _lookback(request, mailbox: str) -> None:
    """Set, or with an empty value reset, the intake's first-scan lookback (``action=lookback``)."""
    form = LookbackForm(request.POST)
    if not form.is_valid():
        messages.error(request, f"The first-scan lookback was not saved: {_first_error(form)}")
        return
    hours = form.cleaned_data["lookback_hours"]
    previous = intake_state.set_lookback(mailbox, hours, actor=request.user)
    value = _hours(hours) if hours is not None else f"the default ({_hours(intake_state.default_lookback_hours())})"
    if previous == hours:
        messages.info(request, f"The intake's first-scan lookback for {mailbox} is already {value}; nothing changed.")
        return
    checkpoint = intake_state.state_for(mailbox).checkpoint_at
    note = (
        f" It applies only while the intake has no checkpoint, and it has one ({when(checkpoint)}): use Rescan since "
        "to read older mail now."
        if checkpoint
        else " The first scan reads that far back."
    )
    messages.success(request, f"Intake first-scan lookback for {mailbox} set to {value}.{note}")
