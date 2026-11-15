import re

from unfold.widgets import (
    UnfoldAdminFileFieldWidget,
    UnfoldAdminTextareaWidget,
    UnfoldAdminTextInputWidget,
)

_THUMBPRINT_RE = re.compile(r"[0-9A-F]{40}")


class WriteOnlyTextarea(UnfoldAdminTextareaWidget):
    """A textarea that never renders a submitted value back."""

    def format_value(self, value):
        return None


def normalize_thumbprint(value) -> str:
    """Upper-case hex without the colons and spaces Entra, OpenSSL or Keychain may show."""
    return "".join(str(value or "").replace(":", "").split()).upper()


class ThumbprintInput(UnfoldAdminTextInputWidget):
    """Renders a submitted value back only as a well-formed SHA-1 thumbprint, so nothing else typed here is echoed."""

    def format_value(self, value):
        thumbprint = normalize_thumbprint(value)
        return thumbprint if _THUMBPRINT_RE.fullmatch(thumbprint) else None


class CertificateTextarea(UnfoldAdminTextareaWidget):
    """Renders only ``canonical_pem``, which the form sets once the pasted text loaded as one certificate."""

    canonical_pem = None

    def format_value(self, value):
        return self.canonical_pem


def _file_widget(accept: str):
    return UnfoldAdminFileFieldWidget(attrs={"accept": accept})
