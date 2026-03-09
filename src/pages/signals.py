"""
Signal handlers for cache invalidation when layout content is updated.
"""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import FooterContent, Menu


@receiver([post_save, post_delete], sender=Menu)
@receiver([post_save, post_delete], sender=FooterContent)
def invalidate_layout_cache(sender, instance, **kwargs):
    """Clear layout cache when Menu or FooterContent is saved or deleted."""
    cache.delete("layout:data")
