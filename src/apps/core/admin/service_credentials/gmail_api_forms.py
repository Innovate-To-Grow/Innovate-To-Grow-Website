"""Forms for the Gmail API key pages: install a service-account key, remove it, run the access check.

These are plain forms on their own admin pages, never part of the config's change form, so the confirm-on-save step
never stashes a key in the session or cache. Nothing entered as a key is rendered back: the key box is write-only,
file inputs never render a value, and every error is fixed text (``key.parsing``).
"""

from django import forms
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from unfold.widgets import (
    UnfoldAdminFileFieldWidget,
    UnfoldAdminTextareaWidget,
    UnfoldAdminTextInputWidget,
    UnfoldBooleanWidget,
)

from apps.core.services.email.gmail.key.parsing import KeyInputError, parse_key

from .microsoft_graph_certificate_forms import REMOVE_WORD, REMOVE_WORD_REQUIRED, WriteOnlyTextarea

KEY_FIELD = "service_account_key"
FILE_FIELD = "service_account_key_file"
TEXT_AND_FILE = "Paste the key file or upload it, not both."
KEY_REQUIRED = "Paste the service-account key file or upload it."
FILE_TOO_LARGE = "This file is larger than a service-account key file can be."
_TEXTAREA_ATTRS = {"rows": 10, "spellcheck": "false", "autocomplete": "off", "class": "font-mono"}


class InstallKeyForm(forms.Form):
    service_account_key = forms.CharField(
        required=False,
        strip=False,
        label="Service-account key (JSON)",
        help_text="The whole JSON key file Google Cloud created for the service account. It is tested with Google, "
        "stored in the credential store and never shown again. Delete the downloaded file afterwards.",
        widget=WriteOnlyTextarea(attrs=_TEXTAREA_ATTRS),
    )
    service_account_key_file = forms.FileField(
        required=False,
        label="…or the key file",
        help_text="The .json file (read in memory, never saved).",
        widget=UnfoldAdminFileFieldWidget(attrs={"accept": ".json,application/json"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parsed = None

    @sensitive_variables()
    def clean(self):
        cleaned = super().clean()
        text = cleaned.get(KEY_FIELD) or ""
        upload = cleaned.get(FILE_FIELD)
        if text.strip() and upload:
            self.add_error(FILE_FIELD, TEXT_AND_FILE)
            return cleaned
        if upload and upload.size > settings.GMAIL_API["key_max_input_bytes"]:
            self.add_error(FILE_FIELD, FILE_TOO_LARGE)
            return cleaned
        data = b"".join(upload.chunks()) if upload else text
        if not data or not str(data).strip():
            self.add_error(KEY_FIELD, KEY_REQUIRED)
            return cleaned
        try:
            self.parsed = parse_key(data)
        except KeyInputError as exc:
            self.add_error(FILE_FIELD if upload else KEY_FIELD, exc.message)
        return cleaned


class RemoveKeyForm(forms.Form):
    confirmation = forms.CharField(
        label=f"Type {REMOVE_WORD} to confirm",
        widget=UnfoldAdminTextInputWidget(attrs={"autocomplete": "off"}),
    )
    reason = forms.CharField(
        max_length=255,
        label="Reason",
        help_text="Recorded in the admin history.",
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 3}),
    )
    switch_to_ses = forms.BooleanField(
        required=False,
        label="Also switch email delivery to AWS SES",
        help_text="Done only when SES is ready. Otherwise email stays on the Gmail API, and fails until a key is "
        "installed again.",
        widget=UnfoldBooleanWidget,
    )

    def clean_confirmation(self):
        if self.cleaned_data["confirmation"].strip() != REMOVE_WORD:
            raise forms.ValidationError(REMOVE_WORD_REQUIRED)
        return REMOVE_WORD


class AccessCheckForm(forms.Form):
    send = forms.BooleanField(
        required=False,
        initial=True,
        label="Send a probe email from each account to itself",
        help_text="It counts against the account's daily sending limit and stays in its Sent folder.",
        widget=UnfoldBooleanWidget,
    )
    breadth = forms.BooleanField(
        required=False,
        initial=True,
        label="Check that no broader scope is delegated",
        help_text="Token requests only; skipping it makes the run NOT A COMPLETE VALIDATION (nothing is recorded).",
        widget=UnfoldBooleanWidget,
    )
