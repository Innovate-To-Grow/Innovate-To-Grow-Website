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

from .models import CMSBlock, CMSPage, FooterContent, Menu, NewsArticle, SiteSettings, StyleSheet
from .views.views import LAYOUT_CACHE_KEY, LAYOUT_STYLESHEET_CACHE_KEY


def _clear_layout_caches():
    cache.delete(LAYOUT_CACHE_KEY)
    cache.delete(LAYOUT_STYLESHEET_CACHE_KEY)


@receiver([post_save, post_delete], sender=Menu)
@receiver([post_save, post_delete], sender=FooterContent)
@receiver([post_save, post_delete], sender=SiteSettings)
# noinspection PyUnusedLocal
def invalidate_layout_cache(sender, instance, **kwargs):
    """Clear layout caches when Menu, FooterContent, or SiteSettings change."""
    transaction.on_commit(_clear_layout_caches)


@receiver([post_save, post_delete], sender=StyleSheet)
# noinspection PyUnusedLocal
def invalidate_stylesheet_cache(sender, instance, **kwargs):
    """Clear layout caches when a StyleSheet is saved or deleted."""
    transaction.on_commit(_clear_layout_caches)


@receiver(pre_save, sender=CMSPage)
# noinspection PyUnusedLocal
def stash_old_cms_route(sender, instance, **kwargs):
    """Remember the old route before save so we can clear its cache in post_save."""
    if instance.pk:
        try:
            old = CMSPage.objects.filter(pk=instance.pk).values_list("route", flat=True).first()
            instance._old_route = old
        except (CMSPage.DoesNotExist, ValueError):
            instance._old_route = None
    else:
        instance._old_route = None


@receiver([post_save, post_delete], sender=CMSPage)
# noinspection PyUnusedLocal
def invalidate_cms_page_cache(sender, instance, **kwargs):
    """Clear CMS page cache when a CMSPage is saved or deleted."""
    route = instance.route
    old_route = getattr(instance, "_old_route", None)

    def _clear():
        cache.delete(f"cms:page:{route}")
        if old_route and old_route != route:
            cache.delete(f"cms:page:{old_route}")
        _clear_layout_caches()

    transaction.on_commit(_clear)


@receiver([post_save, post_delete], sender=CMSBlock)
# noinspection PyUnusedLocal
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


@receiver([post_save, post_delete], sender=NewsArticle)
# noinspection PyUnusedLocal
def invalidate_news_cache(sender, instance, **kwargs):
    """Clear news list cache when a NewsArticle is saved or deleted."""
    transaction.on_commit(lambda: cache.delete("news:list"))
