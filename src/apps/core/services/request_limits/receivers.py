"""Keep each process's policy view fresh: a saved or deleted policy or Smart state is re-read after the commit,
and a settings change (``override_settings`` in tests) at once. Other processes pick a change up within
``controller.state_refresh_seconds``. ``connect`` runs from ``CoreConfig.ready``."""

from django.core.signals import setting_changed
from django.db import transaction
from django.db.models.signals import post_delete, post_save

from apps.core.models import RequestRateLimitPolicy, RequestRateLimitState

from .runtime import registry

WATCHED_SETTINGS = frozenset({"REQUEST_RATE_LIMITS", "CACHES"})


def _row_changed(sender, raw=False, **kwargs):
    if not raw:
        transaction.on_commit(registry.invalidate, robust=True)


def _setting_changed(sender, setting, **kwargs):
    if setting in WATCHED_SETTINGS:
        registry.invalidate()


def connect() -> None:
    for model in (RequestRateLimitPolicy, RequestRateLimitState):
        uid = f"request_limits:{model._meta.label_lower}"
        post_save.connect(_row_changed, sender=model, dispatch_uid=f"{uid}:save")
        post_delete.connect(_row_changed, sender=model, dispatch_uid=f"{uid}:delete")
    setting_changed.connect(_setting_changed, dispatch_uid="request_limits:settings")
