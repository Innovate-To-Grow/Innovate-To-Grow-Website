"""The part of Helpdesk → Settings that decides what the helpdesk sends: shadow mode, the acknowledgement switch and
text, and the notification switch. Only an I2G Master (superuser) changes them; everyone else sees them read-only in
words (On / Off, the text with its line breaks) with the reason, and the form does not take them from anyone else.
The acknowledgement text is stored with LF line ends (the browser posts CRLF, so an untouched text is no change) and
may use only the known placeholders.
"""

from django import forms
from django.template.defaultfilters import linebreaksbr
from django.utils.html import format_html
from unfold.decorators import display

from ...services.outbound.compose import unknown_placeholders

LABELS = {
    "shadow_mode": "Shadow mode (nothing is sent)",
    "send_acknowledgement": "Send an acknowledgement",
    "acknowledgement_text": "Acknowledgement text",
    "notify_assignment": "Notify staff of assignments",
    "auto_close_resolved_days": "Auto-close resolved tickets after (days)",
    "sla_warning_percent": "SLA at risk after (% of its time)",
}
MASTER_ONLY = "Only an I2G Master can change these: they decide what the helpdesk sends from the site's address."
# What makes the helpdesk send mail from the site's address, and what its automatic email says: an I2G Master's
# decision, not every Helpdesk grant holder's (a compromised helpdesk account must not turn it into a mailer).
SENDING_FIELDS = ("shadow_mode", "send_acknowledgement", "acknowledgement_text", "notify_assignment")
SHOWN = {field: f"{field}_shown" for field in SENDING_FIELDS}


class SettingsForm(forms.ModelForm):
    def clean_acknowledgement_text(self):
        text = str(self.cleaned_data.get("acknowledgement_text") or "").replace("\r\n", "\n")
        unknown = unknown_placeholders(text)
        if unknown:
            raise forms.ValidationError(
                f"Unknown placeholder{'s' if len(unknown) != 1 else ''}: {', '.join(unknown)}. "
                "Use {ticket} (and {requester_name} or {subject}, which lose any link)."
            )
        return text


def _master(request) -> bool:
    return bool(getattr(request.user, "is_superuser", False))


class SendingFieldsMixin:
    """For ``HelpdeskSettingsAdmin``: the sending fields for an I2G Master, their read-only form for everyone else."""

    form = SettingsForm
    SENDING_FIELDS = SENDING_FIELDS

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if _master(request):
            return fieldsets
        shown = []
        for title, options in fieldsets:
            fields = tuple(SHOWN.get(name, name) for name in options["fields"])
            if any(name in SHOWN.values() for name in fields):
                options = {**options, "description": f"{options.get('description', '')} {MASTER_ONLY}".strip()}
            shown.append((title, {**options, "fields": fields}))
        return shown

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(super().get_readonly_fields(request, obj))
        return fields if _master(request) else (*fields, *SHOWN.values())

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        for name, label in LABELS.items():
            if name in form.base_fields:
                form.base_fields[name].label = label
        return form

    @display(description=LABELS["shadow_mode"])
    def shadow_mode_shown(self, obj):
        return "On" if obj.shadow_mode else "Off"

    @display(description=LABELS["send_acknowledgement"])
    def send_acknowledgement_shown(self, obj):
        return "On" if obj.send_acknowledgement else "Off"

    @display(description=LABELS["acknowledgement_text"])
    def acknowledgement_text_shown(self, obj):
        return format_html("<div>{}</div>", linebreaksbr(obj.acknowledgement_text))

    @display(description=LABELS["notify_assignment"])
    def notify_assignment_shown(self, obj):
        return "On" if obj.notify_assignment else "Off"
