"""A per-view scope's seed, and the whole numbers a deployment may set for one from the environment."""

import os

from django.core.exceptions import ImproperlyConfigured

MINUTE = 60
HOUR = 3_600


def _env_count(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        number = int(value)
    except ValueError:
        raise ImproperlyConfigured(f"{name} must be a whole number.") from None
    return max(1, number)


def _view(label, tier, parent, requests, period, description, *, fixed=False):
    return {
        "label": label,
        "description": description,
        "tier": tier,
        "identity": "view",
        "requests": requests,
        "period_seconds": period,
        "smart_enabled": True,
        "smart_floor": None,
        "fixed": fixed,
        "enabled": True,
        "identity_ceiling": None,
        "global_cap": None,
        "parent": parent,
    }
