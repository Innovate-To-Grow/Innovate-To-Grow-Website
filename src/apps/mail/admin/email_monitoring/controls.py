"""Email Monitoring → Bounce processing: the card's "Rescan since" and first-scan lookback forms.

Both change only the bounce processor's state row, through ``apps.core.services.email.bounces.state``, which applies
the bounds (``bounce_max_lookback_days``), the lease rule and the audit trail (an admin history line and a log line).
Neither starts a scan: the next scheduled scan, or "Scan now", reads the Inbox. The view that dispatches to them has
already required the Mail app; every message names what changed, or why nothing did.
"""

from django import forms
from django.conf import settings
from django.contrib import messages
from django.utils import formats, timezone

from apps.core.services.email.bounces import state as bounce_state

# How a time is shown in a message: the site's time zone, to the minute, with the zone's abbreviation.
WHEN = "M j, Y, H:i T"


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
        low, high = bounce_state.lookback_bounds()
        if hours is not None and not low <= hours <= high:
            raise forms.ValidationError(
                f"enter {low:,} to {high:,} hours, or leave it empty for the default "
                f"({bounce_state.default_lookback_hours():,} hours)."
            )
        return hours


def _hours(hours: int) -> str:
    return f"{hours:,} hour{'' if hours == 1 else 's'}"


def _first_error(form: forms.Form) -> str:
    return next(iter(form.errors.values()))[0]


def rescan(request, mailbox: str) -> None:
    """Move the mailbox's checkpoint back to the posted time (``action=rescan``)."""
    if not settings.EMAIL_MONITORING["bounce_processing_enabled"]:
        messages.warning(request, "Bounce processing is turned off (EMAIL_BOUNCE_PROCESSING_ENABLED).")
        return
    form = RescanForm(request.POST)
    if not form.is_valid():
        messages.error(request, f"The checkpoint was not moved: {_first_error(form)}")
        return
    result = bounce_state.rescan_since(mailbox, form.cleaned_data["since"], actor=request.user)
    level, text = _rescan_message(mailbox, result)
    messages.add_message(request, level, text)


def _rescan_message(mailbox: str, result: bounce_state.Rescan) -> tuple[int, str]:
    since = when(result.since)
    if result.status == "moved":
        moved = (
            f"the checkpoint moved back from {when(result.previous)} to {since}"
            if result.previous
            else f"its first scan reads mail received since {since}"
        )
        then = (
            "once bounce processing is resumed (it is paused)"
            if result.paused
            else "at the next scheduled scan, or sooner with Scan now"
        )
        return messages.SUCCESS, (
            f"Rescan set for {mailbox}: {moved}. The Inbox is read again from that time {then}; reports already "
            "recorded are skipped, so none is counted twice."
        )
    if result.status == "not_earlier":
        return messages.INFO, (
            f"Nothing changed: the checkpoint ({when(result.previous)}) is already at or before {since}, so the next "
            "scan reads from there anyway."
        )
    if result.status == "running":
        return messages.WARNING, (
            f"A scan of {mailbox} is running, so the checkpoint was not moved (the scan would save its own over it). "
            f"Try again in a minute: the scan holds the mailbox until {when(result.lease_until)} at the latest."
        )
    if result.status == "future":
        return messages.ERROR, f"The checkpoint was not moved: {since} is in the future."
    return messages.ERROR, (
        f"The checkpoint was not moved: {since} is more than {bounce_state.max_lookback_days()} days ago. Choose "
        f"{when(result.earliest)} or later."
    )


def lookback(request, mailbox: str) -> None:
    """Set, or with an empty value reset, the mailbox's first-scan lookback (``action=lookback``)."""
    form = LookbackForm(request.POST)
    if not form.is_valid():
        messages.error(request, f"The first-scan lookback was not saved: {_first_error(form)}")
        return
    hours = form.cleaned_data["lookback_hours"]
    previous = bounce_state.set_lookback(mailbox, hours, actor=request.user)
    value = _hours(hours) if hours is not None else f"the default ({_hours(bounce_state.default_lookback_hours())})"
    if previous == hours:
        messages.info(request, f"The first-scan lookback for {mailbox} is already {value}; nothing changed.")
        return
    checkpoint = bounce_state.state_for(mailbox).checkpoint_at
    note = (
        f" It applies only while the mailbox has no checkpoint, and it has one ({when(checkpoint)}): use Rescan since "
        "to read older mail now."
        if checkpoint
        else " The first scan reads that far back."
    )
    messages.success(request, f"First-scan lookback for {mailbox} set to {value}.{note}")
