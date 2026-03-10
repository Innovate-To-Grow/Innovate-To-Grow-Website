"""
Forms for the mail app — Google Account configuration and email composition.
"""

import json

from django import forms

from .models import GoogleAccount


class GoogleAccountForm(forms.ModelForm):
    """Form for creating/editing Gmail API accounts with JSON validation."""

    service_account_json = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 10, "class": "vLargeTextField"}),
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

    to = forms.CharField(
        max_length=1000,
        widget=forms.TextInput(attrs={"class": "vTextField", "placeholder": "recipient@example.com"}),
        help_text="Comma-separated email addresses.",
    )
    cc = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.TextInput(attrs={"class": "vTextField", "placeholder": "cc@example.com"}),
    )
    bcc = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.TextInput(attrs={"class": "vTextField", "placeholder": "bcc@example.com"}),
    )
    subject = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 15, "class": "vLargeTextField"}),
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
