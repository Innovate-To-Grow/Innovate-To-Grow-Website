"""The event admin form."""

from django import forms

from ...models import Event


class EventAdminForm(forms.ModelForm):
    contact_dependency_hints = {
        "verify_phone": "event-phone-dependency-hint",
        "require_phone": "event-phone-dependency-hint",
        "verify_secondary_email": "event-secondary-email-dependency-hint",
        "require_secondary_email": "event-secondary-email-dependency-hint",
    }

    class Meta:
        model = Event
        fields = "__all__"
        labels = {
            "collect_phone": "Collect",
            "verify_phone": "Verify if provided",
            "require_phone": "Required",
            "allow_secondary_email": "Collect",
            "verify_secondary_email": "Verify if provided",
            "require_secondary_email": "Required",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if (
            not self.is_bound
            and not self.instance._state.adding
            and self.instance.end_date is None
            and self.instance.date is not None
        ):
            self.initial["end_date"] = self.instance.date
        for field_name, hint_id in self.contact_dependency_hints.items():
            widget = self.fields[field_name].widget
            described_by = str(widget.attrs.get("aria-describedby") or "").split()
            if hint_id not in described_by:
                described_by.append(hint_id)
            widget.attrs["aria-describedby"] = " ".join(described_by)

    class Media:
        css = {"all": ("event/css/event_admin.css",)}
        js = ("event/js/event_admin.js",)
