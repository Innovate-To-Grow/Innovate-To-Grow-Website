"""
Signal handlers for cache invalidation when layout or CMS content is updated.

All cache deletions are deferred via ``transaction.on_commit`` so they execute
only after the database transaction commits.  This prevents a race where a
concurrent request re-caches stale data that hasn't been committed yet.
"""

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import CMSBlock, CMSPage, FooterContent, GoogleSheetSource, Menu, SiteSettings


@receiver([post_save, post_delete], sender=Menu)
@receiver([post_save, post_delete], sender=FooterContent)
@receiver([post_save, post_delete], sender=SiteSettings)
def invalidate_layout_cache(sender, instance, **kwargs):
    """Clear layout cache when Menu or FooterContent is saved or deleted."""
    transaction.on_commit(lambda: cache.delete("layout:data"))


@receiver([post_save, post_delete], sender=GoogleSheetSource)
def invalidate_sheet_cache(sender, instance, **kwargs):
    """Clear sheet data cache when a GoogleSheetSource is saved or deleted."""
    slug = instance.slug

    def _clear():
        cache.delete(f"sheets:{slug}:data")
        cache.delete(f"sheets:{slug}:stale")

    transaction.on_commit(_clear)


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
    route = instance.route
    old_route = getattr(instance, "_old_route", None)

    def _clear():
        cache.delete(f"cms:page:{route}")
        if old_route and old_route != route:
            cache.delete(f"cms:page:{old_route}")
        cache.delete("layout:data")

    transaction.on_commit(_clear)


@receiver([post_save, post_delete], sender=CMSBlock)
def invalidate_cms_block_cache(sender, instance, **kwargs):
    """Clear CMS page cache when a CMSBlock is saved or deleted."""
    page_id = instance.page_id
    if not page_id:
        return

    def _clear():
        try:
            page = CMSPage.objects.get(pk=page_id)
            cache.delete(f"cms:page:{page.route}")
        except CMSPage.DoesNotExist:
            pass

    transaction.on_commit(_clear)
