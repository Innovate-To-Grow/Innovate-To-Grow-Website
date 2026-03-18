"""
Signal handlers for cache invalidation when layout or CMS content is updated.
"""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import CMSBlock, CMSPage, FooterContent, GoogleSheetSource, Menu, SiteSettings


@receiver([post_save, post_delete], sender=Menu)
@receiver([post_save, post_delete], sender=FooterContent)
@receiver([post_save, post_delete], sender=SiteSettings)
def invalidate_layout_cache(sender, instance, **kwargs):
    """Clear layout cache when Menu or FooterContent is saved or deleted."""
    cache.delete("layout:data")


@receiver([post_save, post_delete], sender=GoogleSheetSource)
def invalidate_sheet_cache(sender, instance, **kwargs):
    """Clear sheet data cache when a GoogleSheetSource is saved or deleted."""
    cache.delete(f"sheets:{instance.slug}:data")
    cache.delete(f"sheets:{instance.slug}:stale")


@receiver(pre_save, sender=CMSPage)
def stash_old_cms_route(sender, instance, **kwargs):
    """Remember the old route before save so we can clear its cache in post_save."""
    if instance.pk:
        try:
            old = CMSPage.all_objects.filter(pk=instance.pk).values_list("route", flat=True).first()
            instance._old_route = old
        except Exception:
            instance._old_route = None
    else:
        instance._old_route = None


@receiver([post_save, post_delete], sender=CMSPage)
def invalidate_cms_page_cache(sender, instance, **kwargs):
    """Clear CMS page cache when a CMSPage is saved or deleted."""
    cache.delete(f"cms:page:{instance.route}")
    # Also clear old route cache if route was changed
    old_route = getattr(instance, "_old_route", None)
    if old_route and old_route != instance.route:
        cache.delete(f"cms:page:{old_route}")
    cache.delete("layout:data")


@receiver([post_save, post_delete], sender=CMSBlock)
def invalidate_cms_block_cache(sender, instance, **kwargs):
    """Clear CMS page cache when a CMSBlock is saved or deleted."""
    if instance.page_id:
        try:
            page = CMSPage.objects.get(pk=instance.page_id)
            cache.delete(f"cms:page:{page.route}")
        except CMSPage.DoesNotExist:
            pass
