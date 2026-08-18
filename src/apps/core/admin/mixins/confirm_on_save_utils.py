import logging
import re
import uuid
from datetime import date, datetime

from django import forms
from django.db import models
from django.http import QueryDict
from django.utils.timezone import is_aware

logger = logging.getLogger(__name__)

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


def compute_add_diff(form):
    """Compute diff for a new object being added."""
    diff = []
    for field_name in form.fields:
        if field_name in form.cleaned_data:
            value = form.cleaned_data[field_name]
            label = form.fields[field_name].label or field_name
            diff.append(
                {
                    "field": field_name,
                    # str() resolves lazy gettext labels — the diff is JSON-serialized
                    # into the session, and a __proxy__ would raise at session save.
                    "label": str(label),
                    "new_value": (REDACTED if is_sensitive_field(field_name, form) else format_field_value(value)),
                }
            )
    return diff


def compute_change_diff(model_class, object_id, form):
    """Compute diff for changed fields on an existing object."""
    if not form.changed_data:
        return []

    try:
        old_obj = model_class.objects.get(pk=object_id)
    except model_class.DoesNotExist:
        return []

    diff = []
    for field_name in form.changed_data:
        if field_name not in form.fields:
            continue
        label = form.fields[field_name].label or field_name
        new_value = form.cleaned_data.get(field_name)

        try:
            field = model_class._meta.get_field(field_name)
            old_value = getattr(old_obj, field_name)
            if isinstance(field, models.ForeignKey):
                old_value = getattr(old_obj, field_name)
        except Exception:
            old_value = getattr(old_obj, field_name, None)

        sensitive = is_sensitive_field(field_name, form)
        diff.append(
            {
                "field": field_name,
                # str() resolves lazy gettext labels — the diff is JSON-serialized
                # into the session, and a __proxy__ would raise at session save.
                "label": str(label),
                "old_value": REDACTED if sensitive else format_field_value(old_value),
                "new_value": REDACTED if sensitive else format_field_value(new_value),
            }
        )
    return diff


def compute_formsets_diff(formsets):
    """Summarize added, changed and deleted inline rows across validated ``formsets``.

    Returns rows in the same shape as the main-form diff so the confirmation template can render them
    without changes. Only rows that actually differ are reported, so a page whose inlines were left
    alone still yields an empty list (and a genuinely no-op save still skips the interstitial).
    """
    diff = []
    for formset in formsets or []:
        label = str(getattr(formset.model._meta, "verbose_name", formset.model.__name__)).capitalize()
        for form in formset.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE"):
                if form.instance.pk and not form.instance._state.adding:
                    diff.append(
                        {
                            "field": f"{formset.prefix}-delete",
                            "label": f"{label} (removed)",
                            "old_value": str(form.instance),
                            "new_value": "-",
                        }
                    )
                continue
            if form.instance._state.adding:
                diff.append(
                    {
                        "field": f"{formset.prefix}-add",
                        "label": f"{label} (added)",
                        "old_value": "-",
                        "new_value": _describe_inline_row(form),
                    }
                )
            elif form.changed_data:
                diff.append(
                    {
                        "field": f"{formset.prefix}-change",
                        "label": f"{label} ({str(form.instance)})",
                        "old_value": ", ".join(sorted(form.changed_data)),
                        "new_value": _describe_inline_row(form, only=form.changed_data),
                    }
                )
    return diff


def _describe_inline_row(form, only=None):
    names = only if only is not None else [name for name in form.fields if name not in ("id", "DELETE")]
    parts = []
    for name in names:
        if name in ("id", "DELETE") or name not in form.cleaned_data:
            continue
        value = REDACTED if is_sensitive_field(name, form) else summarize_large_value(form.cleaned_data[name])
        parts.append(f"{name}={value}")
    return ", ".join(parts) or "-"


def compute_delete_diff(obj):
    """Compute diff for an object being deleted — shows all current field values."""
    diff = []
    for field in obj._meta.get_fields():
        if not hasattr(field, "column"):
            continue
        if field.name in ("id", "pk"):
            continue
        try:
            value = getattr(obj, field.name)
            label = getattr(field, "verbose_name", field.name)
            if isinstance(label, str):
                label = label.capitalize()
            if is_sensitive_field(field.name):
                # A pbkdf2 hash is ~80 chars, under format_field_value's 200-char truncation, so the
                # whole thing used to be written into the delete-confirmation HTML.
                shown = REDACTED
            else:
                shown = summarize_large_value(value)
            diff.append(
                {
                    "field": field.name,
                    "label": str(label),
                    "value": shown,
                }
            )
        except Exception as exc:
            logger.debug("Skipping field %s in delete diff: %s", field.name, exc)
    return diff


def summarize_large_value(value):
    """Format a value, replacing a long blob with a size summary instead of a truncated prefix.

    A 200-char slice of a base64 ``data:`` URI is noise that crowds out the fields an admin actually
    needs to read on a delete-confirmation page.
    """
    if isinstance(value, str) and len(value) > 200:
        if value.startswith("data:"):
            kind = value[5 : value.find(";")] or "binary"
            return f"<{kind} data, {len(value) // 1024} KB>"
        return f"<{len(value)} characters>"
    return format_field_value(value)


def format_field_value(value):
    """Format a field value for human-readable display."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        fmt = "%Y-%m-%d %H:%M:%S"
        if is_aware(value):
            fmt += " %Z"
        return value.strftime(fmt)
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, models.Model):
        return str(value)
    if isinstance(value, list | dict):
        import json

        try:
            return json.dumps(value, ensure_ascii=False, default=str)[:200]
        except (TypeError, ValueError):
            return str(value)[:200]
    if isinstance(value, models.QuerySet):
        return ", ".join(str(v) for v in value[:10])
    value_str = str(value)
    if len(value_str) > 200:
        return value_str[:200] + "..."
    return value_str
