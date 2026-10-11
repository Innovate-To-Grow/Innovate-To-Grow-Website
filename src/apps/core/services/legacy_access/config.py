"""Feature configuration for the Legacy viewer."""

from django.conf import settings


def legacy_view_is_enabled() -> bool:
    """Return the feature flag without treating the string ``false`` as true."""

    value = getattr(settings, "LEGACY_VIEW_ENABLED", False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
