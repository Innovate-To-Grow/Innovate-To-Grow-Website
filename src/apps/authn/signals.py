"""
Signal handlers that fire member-to-Google-Sheet sync on member-related writes.

Wires `post_save` and `post_delete` on Member, ContactEmail, and ContactPhone
to `schedule_member_sync()`, deferred via `transaction.on_commit` so the sheet
sees only committed state.

`schedule_member_sync()` is itself a no-op when the config is disabled, so
these receivers are safe to leave registered unconditionally.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ContactEmail, ContactPhone, Member

logger = logging.getLogger(__name__)


def _schedule():
    from .services.members.sheet_sync import schedule_member_sync

    schedule_member_sync()


@receiver([post_save, post_delete], sender=Member)
@receiver([post_save, post_delete], sender=ContactEmail)
@receiver([post_save, post_delete], sender=ContactPhone)
# noinspection PyUnusedLocal
def schedule_member_sync_on_change(sender, **kwargs):
    from apps.core.services.background_jobs import jobs_enabled

    if jobs_enabled():
        # A direct insert participates in any surrounding transaction, giving
        # account mutations and their outbox row one commit boundary.
        #
        # The savepoint matters: this runs from post_save inside the admin's transaction, and
        # ``_enqueue_durable_sync`` takes ``select_for_update`` on the pending BackgroundJob row. A
        # lock timeout or DB error here used to propagate out and roll back the whole member save, so
        # a sheet-sync hiccup failed an unrelated admin edit. Roll back only the enqueue and fall
        # through to the deferred path instead.
        try:
            with transaction.atomic():
                _schedule()
            return
        except Exception:
            logger.exception("Could not enqueue the member sheet sync inline; deferring to commit")
    transaction.on_commit(_schedule, robust=True)
