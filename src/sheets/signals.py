"""Signal handlers for cache invalidation when sheet sources are updated."""

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import GoogleSheetSource


@receiver([post_save, post_delete], sender=GoogleSheetSource)
def invalidate_sheet_cache(sender, instance, **kwargs):
    """Clear sheet data cache when a GoogleSheetSource is saved or deleted."""
    slug = instance.slug

    def _clear():
        cache.delete(f"sheets:{slug}:data")
        cache.delete(f"sheets:{slug}:stale")
        cache.delete("layout:data")

    transaction.on_commit(_clear)
