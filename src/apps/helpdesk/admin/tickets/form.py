"""The ticket page's form, ServiceNow style.

- Impact and urgency set the priority (read-only); a form posted without them keeps the ticket's own values.
- The assignee is a member of the assignment group when the group has members (``tickets.membership_problem``).
- Resolving or closing needs a resolution code, and a resolved or closed ticket keeps one.
- The Status list offers neither Merged (only a merge makes one), Spam (the queue's "Mark as spam", behind its typed
  confirmation) nor New once the ticket has left it.
- Staff save what they edited: each editable field carries the value the page showed (Django's hidden initial input),
  so only what this person changed is written. A field someone else (or the ingest) changed since the page was
  shown keeps its new value; when both changed the same field, the save is refused with what it is now.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from unfold.widgets import UnfoldAdminTextareaWidget

from ...models import Ticket
from ...services import tickets
from ...services.tickets.changes import RESOLUTION_NOTES_MAX_CHARS

Status = Ticket.Status
# What the ticket page saves (the priority follows from impact and urgency).
EDITABLE = (
    "status",
    "impact",
    "urgency",
    "category",
    "assignment_group",
    "assignee",
    "resolution_code",
    "resolution_notes",
)
RESOLVING = (Status.RESOLVED, Status.CLOSED)


def _text(field, value) -> str:
    """A value as the page submits it, so what the page showed, what was posted and what the row holds compare."""
    if isinstance(value, models.Model):
        value = value.pk
    if value is None:
        return ""
    return str(field.prepare_value(value)).replace("\r\n", "\n").strip()


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = "__all__"
        widgets = {
            "resolution_notes": UnfoldAdminTextareaWidget(attrs={"rows": 3, "maxlength": RESOLUTION_NOTES_MAX_CHARS})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.edited: set[str] = set()
        for name in ("impact", "urgency"):
            if name in self.fields:
                self.fields[name].required = False
        for name in EDITABLE:
            if name in self.fields:
                self.fields[name].show_hidden_initial = True
                # The browser must not restore an older value on Back: it would count as this person's edit.
                self.fields[name].widget.attrs["autocomplete"] = "off"
        status = self.fields.get("status")
        if status is not None:
            current = self.instance.status
            hidden = {Status.MERGED, Status.SPAM} | ({Status.NEW} if current != Status.NEW else set())
            status.choices = [choice for choice in status.choices if choice[0] not in hidden or choice[0] == current]
            # A page shown earlier may still post the status it showed then; it is judged in ``clean``.
            status.valid_value = lambda value: value in Status.values

    def clean_resolution_notes(self):
        notes = str(self.cleaned_data.get("resolution_notes") or "").replace("\r\n", "\n")
        if len(notes) > RESOLUTION_NOTES_MAX_CHARS:
            raise ValidationError(f"Resolution notes can be at most {RESOLUTION_NOTES_MAX_CHARS:,} characters.")
        return notes

    def clean(self):
        cleaned = super().clean()
        for name in ("impact", "urgency"):
            if name in self.fields and not cleaned.get(name):
                cleaned[name] = getattr(self.instance, name)
        self._keep_what_others_changed(cleaned)
        if "status" in self.edited and cleaned.get("status") in (Status.MERGED, Status.SPAM, Status.NEW):
            self.add_error("status", "This status cannot be chosen on the ticket page.")
        status = cleaned.get("status", self.instance.status)
        code = cleaned.get("resolution_code", self.instance.resolution_code)
        if status in RESOLVING and not code and {"status", "resolution_code"} & self.edited:
            message = "Choose a resolution code to resolve or close the ticket."
            if "status" not in self.edited:
                message = "A resolved or closed ticket keeps its resolution code."
            self.add_error("resolution_code" if "resolution_code" in self.fields else None, message)
        if {"assignment_group", "assignee"} & self.edited:
            group = cleaned.get("assignment_group", self.instance.assignment_group)
            problem = tickets.membership_problem(group, cleaned.get("assignee", self.instance.assignee))
            if problem:
                self.add_error("assignee" if "assignee" in self.fields else None, problem)
        return cleaned

    def _keep_what_others_changed(self, cleaned: dict) -> None:
        """Keep only this person's edits in ``cleaned`` (``self.edited``); refuse when someone else changed the same
        field since the page was shown."""
        conflicts = []
        for name in EDITABLE:
            if name not in self.fields or name not in cleaned:
                continue
            field = self.fields[name]
            now = _text(field, self.initial.get(name))
            shown_raw = self.data.get(self[name].html_initial_name)
            shown = now if shown_raw is None else _text(field, shown_raw)
            posted = _text(field, cleaned[name])
            if posted == shown or posted == now:
                # Not edited here (the row keeps what anyone changed meanwhile), or already what it is now.
                cleaned[name] = getattr(self.instance, name)
            elif shown != now:
                conflicts.append(str(field.label or name))
                cleaned[name] = getattr(self.instance, name)
            else:
                self.edited.add(name)
        if conflicts:
            raise ValidationError(
                f"{', '.join(conflicts)} changed while you were editing this ticket (someone else, or a new message). "
                "Reload the page to see the ticket as it is now, then make your change again."
            )
