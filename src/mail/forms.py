"""
Forms for the mail app — Google Account configuration and email composition.
"""

import json

from django import forms

from .models import GoogleAccount


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


class ComposeForm(forms.Form):
    """Form for composing, replying to, or forwarding emails."""

    _input_classes = (
        "w-full border border-base-200 dark:border-base-700 bg-white dark:bg-base-900"
        " text-font-default-light dark:text-font-default-dark rounded-default px-3 py-2 text-sm"
    )

    to = forms.CharField(
        max_length=1000,
        widget=forms.TextInput(attrs={"class": _input_classes, "placeholder": "recipient@example.com"}),
        help_text="Comma-separated email addresses.",
    )
    cc = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.TextInput(attrs={"class": _input_classes, "placeholder": "cc@example.com"}),
    )
    bcc = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.TextInput(attrs={"class": _input_classes, "placeholder": "bcc@example.com"}),
    )
    subject = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={"class": _input_classes}),
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 15, "class": _input_classes + " font-mono"}),
        help_text="HTML content is supported.",
    )
    attachments = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"allow_multiple_selected": True}),
    )

    # Hidden fields for reply/forward threading
    thread_id = forms.CharField(required=False, widget=forms.HiddenInput())
    in_reply_to = forms.CharField(required=False, widget=forms.HiddenInput())
    references = forms.CharField(required=False, widget=forms.HiddenInput())
