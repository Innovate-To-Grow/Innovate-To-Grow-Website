"""The rows a confirmation page shows for an admin add, change or delete, inline rows included."""

import logging

from django.db import models

from .post_data import REDACTED, is_sensitive_field
from .values import format_field_value, summarize_large_value

# The historical logger name: these functions used to live in ``mixins.confirm_on_save_utils``.
logger = logging.getLogger("apps.core.admin.mixins.confirm_on_save_utils")


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


def _inline_row_diff(formset, form, label: str) -> dict | None:
    """The diff row for one inline form, or None when it adds, changes and removes nothing."""
    if form.cleaned_data.get("DELETE"):
        if not form.instance.pk or form.instance._state.adding:
            return None
        return {
            "field": f"{formset.prefix}-delete",
            "label": f"{label} (removed)",
            "old_value": str(form.instance),
            "new_value": "-",
        }
    if form.instance._state.adding:
        return {
            "field": f"{formset.prefix}-add",
            "label": f"{label} (added)",
            "old_value": "-",
            "new_value": _describe_inline_row(form),
        }
    if form.changed_data:
        return {
            "field": f"{formset.prefix}-change",
            "label": f"{label} ({str(form.instance)})",
            "old_value": ", ".join(sorted(form.changed_data)),
            "new_value": _describe_inline_row(form, only=form.changed_data),
        }
    return None


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
            row = _inline_row_diff(formset, form, label)
            if row is not None:
                diff.append(row)
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
