"""A route scope's seed: the values every scope in ``scopes`` and ``critical_scopes`` starts from."""

MINUTE = 60


def _scope(
    label, tier, identity, requests, *, period=MINUTE, global_cap=None, ceiling=None, source=None, fixed=False, **extra
):
    return {
        "label": label,
        "description": extra.pop("description", ""),
        "tier": tier,
        "identity": identity,
        "requests": requests,
        "period_seconds": period,
        "smart_enabled": True,
        # None: the tier's floor (``TIERS``).
        "smart_floor": extra.pop("smart_floor", None),
        "fixed": fixed,
        "enabled": True,
        "identity_ceiling": ceiling,
        "global_cap": global_cap,
        "source_cap": source,
    }
