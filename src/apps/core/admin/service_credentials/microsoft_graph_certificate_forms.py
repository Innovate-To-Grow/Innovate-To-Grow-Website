"""Forms for the Microsoft Graph certificate pages: install a certificate (and its private key), or remove both.

These are plain forms on their own admin pages, never part of the config's change form, so the confirm-on-save
step never stashes a private key in the session or cache. Nothing an admin enters as a key or password is rendered
back: the key box is write-only, and after an error the certificate box shows only the canonical PEM of a
certificate that loaded, never the submitted text (which could hold a key pasted into the wrong box).
"""

import re

from cryptography.hazmat.primitives.serialization import Encoding
from django import forms
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from unfold.widgets import (
    UnfoldAdminFileFieldWidget,
    UnfoldAdminPasswordWidget,
    UnfoldAdminTextareaWidget,
    UnfoldAdminTextInputWidget,
    UnfoldBooleanWidget,
)

from apps.core.models import MicrosoftGraphCertificate
from apps.core.services.email.graph.credential.loaders import as_bytes, load_certificate
from apps.core.services.email.graph.credential.parsing import (
    BUNDLE,
    CERTIFICATE,
    PASSWORD,
    PRIVATE_KEY,
    CertificateInputError,
    parse_certificate_input,
)

TEXT_AND_FILE = "Paste the {what} or upload its file, not both."
FILE_TOO_LARGE = "This file is larger than a certificate or key can be."
THUMBPRINT_FORMAT = "Enter the 40 hexadecimal characters of the SHA-1 thumbprint (colons and spaces are ignored)."
THUMBPRINT_MISMATCH = (
    "This certificate's SHA-1 thumbprint is not the expected one. Check that this is the certificate OIT "
    "registered on the app."
)
REMOVE_WORD = "REMOVE"
REMOVE_WORD_REQUIRED = f"Type {REMOVE_WORD} to confirm."
_THUMBPRINT_RE = re.compile(r"[0-9A-F]{40}")
_TEXTAREA_ATTRS = {"rows": 8, "spellcheck": "false", "autocomplete": "off", "class": "font-mono"}
# Each pasted-or-uploaded input of ``parse_certificate_input``: (text field, file field, what the admin calls it).
_TEXT_OR_FILE_INPUTS = {
    CERTIFICATE: ("certificate_text", "certificate_file", "certificate"),
    PRIVATE_KEY: ("private_key_text", "private_key_file", "private key"),
}


class WriteOnlyTextarea(UnfoldAdminTextareaWidget):
    """A textarea that never renders a submitted value back."""

    def format_value(self, value):
        return None


class CertificateTextarea(UnfoldAdminTextareaWidget):
    """Renders only ``canonical_pem``, which the form sets once the pasted text loaded as one certificate."""

    canonical_pem = None

    def format_value(self, value):
        return self.canonical_pem


def _file_widget(accept: str):
    return UnfoldAdminFileFieldWidget(attrs={"accept": accept})


class InstallCertificateForm(forms.Form):
    bundle = forms.FileField(
        required=False,
        label=".p12 / .pfx file",
        help_text="The certificate and its private key in one file, as macOS Keychain exports it. "
        "Enter its password below. Leave the certificate and private key inputs empty.",
        widget=_file_widget(".p12,.pfx"),
    )
    certificate_text = forms.CharField(
        required=False,
        strip=False,
        label="Certificate",
        help_text="The certificate registered in Entra: PEM (-----BEGIN CERTIFICATE-----) or base64. "
        "No private key here.",
        widget=CertificateTextarea(attrs=_TEXTAREA_ATTRS),
    )
    certificate_file = forms.FileField(
        required=False,
        label="…or certificate file",
        help_text="The .cer file sent to OIT (DER), or a .crt / .pem file.",
        widget=_file_widget(".cer,.crt,.pem,.der"),
    )
    private_key_text = forms.CharField(
        required=False,
        strip=False,
        label="Private key",
        help_text="PEM, PKCS#8 or PKCS#1, optionally encrypted. It is stored in the credential store and never "
        "shown again. Leave it blank to keep the installed key when this certificate re-issues it (same key pair).",
        widget=WriteOnlyTextarea(attrs=_TEXTAREA_ATTRS),
    )
    private_key_file = forms.FileField(
        required=False,
        label="…or private key file",
        help_text="A .key or .pem file.",
        widget=_file_widget(".key,.pem"),
    )
    password = forms.CharField(
        required=False,
        strip=False,
        label="Password / passphrase",
        help_text="The .p12 / .pfx password, or the passphrase of an encrypted private key.",
        widget=UnfoldAdminPasswordWidget(attrs={"autocomplete": "new-password"}, render_value=False),
    )
    expected_sha1 = forms.CharField(
        required=False,
        label="Expected SHA-1 thumbprint",
        help_text="Optional: the thumbprint OIT confirmed, or Entra lists under Certificates & secrets. "
        "The install stops if the certificate's thumbprint differs.",
        widget=UnfoldAdminTextInputWidget(attrs={"autocomplete": "off", "spellcheck": "false"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parsed = None

    def clean_expected_sha1(self):
        value = "".join(self.cleaned_data["expected_sha1"].replace(":", "").split()).upper()
        if value and not _THUMBPRINT_RE.fullmatch(value):
            raise forms.ValidationError(THUMBPRINT_FORMAT)
        return value

    @sensitive_variables()
    def clean(self):
        cleaned = super().clean()
        self._echo_certificate(cleaned.get("certificate_text"))
        inputs = self._inputs()
        if inputs is None or self.errors:
            return cleaned
        try:
            parsed = parse_certificate_input(**inputs, password=cleaned.get("password") or "")
        except CertificateInputError as exc:
            self.add_error(self.field_for(exc.field), exc.message)
            return cleaned
        expected = cleaned.get("expected_sha1")
        if expected and expected != parsed.facts.sha1_thumbprint:
            self.add_error("expected_sha1", THUMBPRINT_MISMATCH)
            return cleaned
        self.parsed = parsed
        return cleaned

    def field_for(self, input_name):
        """The form field an error on *input_name* (a ``parsing`` input) belongs on; None for a form-wide error."""
        if input_name in _TEXT_OR_FILE_INPUTS:
            text_field, file_field, _what = _TEXT_OR_FILE_INPUTS[input_name]
            return file_field if self.cleaned_data.get(file_field) else text_field
        return {BUNDLE: "bundle", PASSWORD: "password"}.get(input_name)

    @sensitive_variables()
    def _inputs(self) -> dict | None:
        """Each input as bytes (pasted text or file content); None after adding an error."""
        inputs = {BUNDLE: self._file_bytes("bundle")}
        for name, (text_field, file_field, what) in _TEXT_OR_FILE_INPUTS.items():
            text = self.cleaned_data.get(text_field) or ""
            if text.strip() and self.cleaned_data.get(file_field):
                self.add_error(file_field, TEXT_AND_FILE.format(what=what))
            inputs[name] = self._file_bytes(file_field) or text
        return None if self.errors else inputs

    def _file_bytes(self, name) -> bytes:
        upload = self.cleaned_data.get(name)
        if not upload:
            return b""
        if upload.size > settings.GRAPH_CERTIFICATE_MAX_INPUT_BYTES:
            self.add_error(name, FILE_TOO_LARGE)
            return b""
        return b"".join(upload.chunks())

    def _echo_certificate(self, text) -> None:
        """Let the certificate box show the pasted certificate again, re-serialised, if it loads on its own."""
        if not (text or "").strip():
            return
        try:
            certificate = load_certificate(as_bytes(text, CERTIFICATE))
        except CertificateInputError:
            return
        self.fields["certificate_text"].widget.canonical_pem = certificate.public_bytes(Encoding.PEM).decode("ascii")


class RemoveCertificatesForm(forms.Form):
    confirmation = forms.CharField(
        label=f"Type {REMOVE_WORD} to confirm",
        widget=UnfoldAdminTextInputWidget(attrs={"autocomplete": "off"}),
    )
    reason = forms.CharField(
        max_length=MicrosoftGraphCertificate._meta.get_field("removal_note").max_length,
        label="Reason",
        help_text="Recorded with the removed certificates and in the admin history.",
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 3}),
    )
    switch_to_ses = forms.BooleanField(
        required=False,
        label="Also switch email delivery to AWS SES",
        help_text="Done only when SES is ready. Otherwise email stays on Microsoft Graph, and fails until a "
        "certificate is installed again.",
        widget=UnfoldBooleanWidget,
    )

    def clean_confirmation(self):
        if self.cleaned_data["confirmation"].strip() != REMOVE_WORD:
            raise forms.ValidationError(REMOVE_WORD_REQUIRED)
        return REMOVE_WORD
