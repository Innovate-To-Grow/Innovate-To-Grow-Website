"""
Validators for page-related fields.

Currently includes nested slug validation used across the Page model and tests.
"""

import re

from django.core.exceptions import ValidationError

_NESTED_SLUG_REGEX = re.compile(r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:/[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)*$")


def validate_nested_slug(value: str):
    """
    Validate a slug that supports nested paths separated by '/'.

    Rules:
    - No leading or trailing slash.
    - No empty segments (i.e., no double slashes).
    - Only lowercase letters, numbers, hyphens, and slashes.
    """
    if not value:
        raise ValidationError("Slug cannot be empty.")

    if value.startswith("/") or value.endswith("/"):
        raise ValidationError("Slug cannot start or end with '/'.")

    if "//" in value:
        raise ValidationError("Slug cannot contain empty segments ('//').")

    if not _NESTED_SLUG_REGEX.match(value):
        raise ValidationError("Slug may only contain lowercase letters, numbers, hyphens, and '/'.")

    return value
