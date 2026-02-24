"""
Signal handlers for cache invalidation when content is updated.
"""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import FooterContent, HomePage, Menu, Page


@receiver([post_save, post_delete], sender=HomePage)
def invalidate_homepage_cache(sender, instance, **kwargs):
    """Clear homepage cache when HomePage is saved or deleted."""
    cache.delete("homepage:active")


@receiver([post_save, post_delete], sender=Page)
def invalidate_page_cache(sender, instance, **kwargs):
    """Clear page cache when a Page is saved or deleted."""
    if instance.slug:
        cache.delete(f"page:slug:{instance.slug}")


@receiver([post_save, post_delete], sender=Menu)
@receiver([post_save, post_delete], sender=FooterContent)
def invalidate_layout_cache(sender, instance, **kwargs):
    """Clear layout cache when Menu or FooterContent is saved or deleted."""
    cache.delete("layout:data")
