"""Signal handlers for CMS cache invalidation."""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import CMSBlock, CMSPage


@receiver([post_save, post_delete], sender=CMSPage)
def invalidate_cms_page_cache(sender, instance, **kwargs):
    """Clear cached CMS page data when a page is saved or deleted."""
    cache.delete(f"cms:page:{instance.route}")


@receiver([post_save, post_delete], sender=CMSBlock)
def invalidate_cms_block_cache(sender, instance, **kwargs):
    """Clear cached CMS page data when a block is saved or deleted."""
    if instance.page_id:
        try:
            page = CMSPage.objects.get(pk=instance.page_id)
            cache.delete(f"cms:page:{page.route}")
        except CMSPage.DoesNotExist:
            pass
