"""Storage housekeeping for System Intelligence models."""

import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import SystemIntelligenceExport

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=SystemIntelligenceExport)
# noinspection PyUnusedLocal
def delete_export_file(sender, instance, **kwargs):
    """Remove the xlsx from storage once the row is gone.

    Runs for every delete path (admin, cleanup command, conversation cascade)
    and waits for the transaction to commit so a rolled-back delete does not
    orphan the row from its file.
    """
    name = instance.file.name if instance.file else ""
    if not name:
        return
    storage = instance.file.storage

    def _remove():
        try:
            storage.delete(name)
        except Exception:  # noqa: BLE001 -- a storage hiccup must not break the delete.
            logger.warning("Could not delete export file %s for export %s", name, instance.pk, exc_info=True)

    transaction.on_commit(_remove)
