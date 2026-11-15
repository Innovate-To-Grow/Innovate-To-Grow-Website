"""Admin POST payloads held while a change awaits confirmation, and which fields count as secrets (masked in every
diff, never stored in the session)."""

import re

from django import forms
from django.http import QueryDict

REDACTED = "********"

# Mirrors apps.core.services.db_tools.safe_orm.constants.SENSITIVE_FIELD_RE, which is already the
# project's policy for the CLI / AI data path. The confirmation diff is rendered to HTML *and*
# JSON-serialized into the DB-backed session, so a raw value here is exposed twice over.
SENSITIVE_FIELD_RE = re.compile(
    r"(password|passwd|secret|token|api_?key|private_?key|credential|salt|hash|signature)",
    re.IGNORECASE,
)

# Names that match the regex but are not secrets worth protecting. ``csrfmiddlewaretoken`` is in
# every admin POST and already lives in the session and cookies; treating it as sensitive pushed
# EVERY confirmation's payload into the short-TTL secrets cache, so a plain text edit expired with
# EXPIRED_PENDING_ERROR once CACHE_FILE_TTL elapsed.
SENSITIVE_FIELD_EXEMPTIONS = frozenset({"csrfmiddlewaretoken"})


def is_sensitive_field(name, form=None) -> bool:
    """Whether a field's value must be masked in a confirmation diff or stored payload."""
    if name in SENSITIVE_FIELD_EXEMPTIONS:
        return False
    if name and SENSITIVE_FIELD_RE.search(str(name)):
        return True
    if form is not None:
        field = form.fields.get(name)
        # Covers unfold.widgets.UnfoldAdminPasswordWidget, which subclasses PasswordInput.
        if field is not None and isinstance(field.widget, forms.PasswordInput):
            return True
    return False


def serialize_post_data(post):
    """Serialize a QueryDict to a JSON-safe dict preserving multi-value keys.

    Sensitive keys are dropped rather than stored: this payload is replayed from the DB-backed
    session, so keeping a plaintext password here left it at rest for the session's lifetime
    (``SESSION_COOKIE_AGE`` is 8 hours in production). Dropping them means a confirmed *add* cannot
    replay a password — see ``ConfirmOnSaveMixin.changeform_view``, which restores them from the
    confirm POST instead.
    """
    return {key: post.getlist(key) for key in post if not is_sensitive_field(key)}


def extract_sensitive_post_data(post):
    """Return only the sensitive keys, for storage outside the session."""
    return {key: post.getlist(key) for key in post if is_sensitive_field(key)}


def deserialize_post_data(data):
    """Reconstruct a mutable QueryDict from serialized data."""
    qd = QueryDict(mutable=True)
    for key, values in data.items():
        qd.setlist(key, values)
    return qd
