"""Stub kept for historical migration references."""

import re

from django.core.exceptions import ValidationError


def validate_nested_slug(value):
    """Validate nested slug format (e.g. 'parent/child'). Stub for migrations."""
    if not re.match(r"^[a-z0-9]+(?:[/-][a-z0-9]+)*$", value):
        raise ValidationError("Invalid nested slug format.")
