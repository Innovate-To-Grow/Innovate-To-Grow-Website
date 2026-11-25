"""The part of Helpdesk → Settings that decides what the helpdesk sends: the labels of its fields, and the form that
keeps the acknowledgement text clean. Every Admin changes shadow mode, the acknowledgement switch and text, and the
notification switch like any other setting. The acknowledgement text is stored with LF line ends (the browser posts
CRLF, so an untouched text is no change) and may use only the known placeholders.
"""

from django import forms

from ...services.outbound.compose import ACKNOWLEDGEMENT_PLACEHOLDERS, unknown_placeholders

LABELS = {
    "shadow_mode": "Shadow mode (nothing is sent)",
    "send_acknowledgement": "Send an acknowledgement",
    "acknowledgement_text": "Acknowledgement text",
    "notify_assignment": "Notify staff of assignments",
    "auto_close_resolved_days": "Auto-close resolved tickets after (days)",
    "sla_warning_percent": "SLA at risk after (% of its time)",
    "spam_scl_threshold": "Spam SCL threshold",
    "bulk_bcl_threshold": "Bulk BCL threshold",
    "body_text_max_chars": "Body text max characters",
    "body_html_max_chars": "Body HTML max characters",
}


class LFTextField(forms.CharField):
    """Text whose line ends are LF whatever the browser posts (CRLF): an untouched text is no change, in the typed
    confirmation and the history too."""

    def to_python(self, value):
        return super().to_python(value).replace("\r\n", "\n")


class SettingsForm(forms.ModelForm):
    class Meta:
        field_classes = {"acknowledgement_text": LFTextField}

    def clean_acknowledgement_text(self):
        text = str(self.cleaned_data.get("acknowledgement_text") or "")
        unknown = unknown_placeholders(text, ACKNOWLEDGEMENT_PLACEHOLDERS)
        if unknown:
            raise forms.ValidationError(
                f"Unknown placeholder{'s' if len(unknown) != 1 else ''}: {', '.join(unknown)}. "
                "Use {ticket} (and {requester_name} or {subject}, which lose any link)."
            )
        return text


class SendingFieldsMixin:
    """For ``HelpdeskSettingsAdmin``: the settings form and its field labels."""

    form = SettingsForm

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        for name, label in LABELS.items():
            if name in form.base_fields:
                form.base_fields[name].label = label
        return form
