"""
Forms for the mail app — Google Account configuration and email composition.
"""

import json

from django import forms

from event.models import Event

from .models import GoogleAccount

_UNFOLD_INPUT = (
    "border border-base-200 bg-white font-medium min-w-20 placeholder-base-400 rounded-default shadow-xs"
    " text-font-default-light text-sm focus:outline-2 focus:-outline-offset-2 focus:outline-primary-600"
    " dark:bg-base-900 dark:border-base-700 dark:text-font-default-dark dark:scheme-dark"
    " px-3 py-2 w-full max-w-2xl"
)

_UNFOLD_SELECT = (
    "border border-base-200 bg-white font-medium rounded-default shadow-xs"
    " text-font-default-light text-sm focus:outline-2 focus:-outline-offset-2 focus:outline-primary-600"
    " dark:bg-base-900 dark:border-base-700 dark:text-font-default-dark dark:scheme-dark"
    " px-3 py-2 w-full max-w-2xl"
)


class GoogleAccountForm(forms.ModelForm):
    """Form for creating/editing Gmail API accounts with JSON validation."""

    service_account_json = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 10,
                "class": (
                    "w-full border border-base-200 dark:border-base-700 bg-white dark:bg-base-900"
                    " text-font-default-light dark:text-font-default-dark rounded-default px-3 py-2 text-sm"
                    " font-mono"
                ),
            }
        ),
        help_text="Paste the full service account JSON key from Google Cloud Console.",
    )

    class Meta:
        model = GoogleAccount
        fields = "__all__"

    def clean_service_account_json(self):
        value = self.cleaned_data["service_account_json"]
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Invalid JSON: {exc}") from exc

        required_keys = {"type", "project_id", "private_key", "client_email"}
        missing = required_keys - set(data.keys())
        if missing:
            raise forms.ValidationError(f"Missing required keys: {', '.join(sorted(missing))}")

        if data.get("type") != "service_account":
            raise forms.ValidationError('The "type" field must be "service_account".')

        return value


RECIPIENT_SOURCE_CHOICES = [
    ("manual", "Manual Entry"),
    ("subscribers", "All Subscribers"),
    ("event", "Event Registrants"),
]


class ComposeForm(forms.Form):
    """Form for composing, replying to, or forwarding emails."""

    recipient_source = forms.ChoiceField(
        choices=RECIPIENT_SOURCE_CHOICES,
        initial="manual",
        widget=forms.RadioSelect(),
    )

    event = forms.ModelChoiceField(
        queryset=Event.objects.all(),
        required=False,
        empty_label="— Select an event —",
        widget=forms.Select(attrs={"class": _UNFOLD_SELECT}),
    )

    include_unsubscribe_link = forms.BooleanField(
        required=False,
        initial=False,
        label="Include unsubscribe link",
        help_text="Adds a 'Manage email preferences' link with 7-day auto-login.",
    )

    to = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.TextInput(attrs={"class": _UNFOLD_INPUT, "placeholder": "recipient@example.com"}),
        help_text="Comma-separated email addresses.",
    )
    cc = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.TextInput(attrs={"class": _UNFOLD_INPUT, "placeholder": "cc@example.com"}),
    )
    bcc = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.TextInput(attrs={"class": _UNFOLD_INPUT, "placeholder": "bcc@example.com"}),
    )
    subject = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={"class": _UNFOLD_INPUT}),
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 15, "class": _UNFOLD_INPUT}),
        help_text="HTML supported. Use {name} for personalization when sending to subscribers or event registrants.",
    )
    attachments = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"allow_multiple_selected": True}),
    )

    # Hidden fields for reply/forward threading
    thread_id = forms.CharField(required=False, widget=forms.HiddenInput())
    in_reply_to = forms.CharField(required=False, widget=forms.HiddenInput())
    references = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("recipient_source", "manual")

        if source == "manual":
            if not cleaned.get("to"):
                self.add_error("to", "Recipients are required for manual entry.")
        elif source == "event":
            if not cleaned.get("event"):
                self.add_error("event", "Please select an event.")

        return cleaned
