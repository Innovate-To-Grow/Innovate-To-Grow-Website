"""
Signal handlers for cache invalidation when layout or CMS content is updated.

All cache deletions are deferred via ``transaction.on_commit`` so they execute
only after the database transaction commits.  This prevents a race where a
concurrent request re-caches stale data that hasn't been committed yet.
"""

import logging

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import (
    CMSBlock,
    CMSEmbedAllowedHost,
    CMSPage,
    FooterContent,
    Menu,
    NewsArticle,
    RouteRedirect,
    SiteSettings,
    StyleSheet,
)
from .services.sanitization.embed_hosts import invalidate_cache as invalidate_embed_host_cache
from .views.layout import LAYOUT_CACHE_KEY, LAYOUT_STYLESHEET_CACHE_KEY

HOMEPAGE_CACHE_KEY = "cms:homepage"

logger = logging.getLogger(__name__)


def _clear_layout_caches():
    cache.delete(LAYOUT_CACHE_KEY)
    cache.delete(LAYOUT_STYLESHEET_CACHE_KEY)


@receiver([post_save, post_delete], sender=CMSEmbedAllowedHost)
# noinspection PyUnusedLocal
def invalidate_embed_host_policy(sender, instance, **kwargs):
    """Keep CSP, backend sanitization, and browser policy on one revision."""

    transaction.on_commit(invalidate_embed_host_cache)


@receiver([post_save, post_delete], sender=Menu)
@receiver([post_save, post_delete], sender=FooterContent)
@receiver([post_save, post_delete], sender=SiteSettings)
# noinspection PyUnusedLocal
def invalidate_layout_cache(sender, instance, **kwargs):
    """Clear layout caches when Menu, FooterContent, or SiteSettings change."""

    def _clear():
        _clear_layout_caches()
        if sender is SiteSettings:
            cache.delete(HOMEPAGE_CACHE_KEY)

    transaction.on_commit(_clear)


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


@receiver(pre_save, sender=RouteRedirect)
# noinspection PyUnusedLocal
def stash_route_redirect_activation(sender, instance, **kwargs):
    """Remember activation state so inactive unmanaged edits skip AWS work."""

    if instance._state.adding:
        instance._edge_sync_previous_is_active = None
        return
    instance._edge_sync_previous_is_active = (
        RouteRedirect.objects.filter(pk=instance.pk).values_list("is_active", flat=True).first()
    )


@receiver([post_save, post_delete], sender=CMSPage)
# noinspection PyUnusedLocal
def invalidate_cms_page_cache(sender, instance, **kwargs):
    """Clear CMS page cache when a CMSPage is saved or deleted."""
    route = instance.route
    old_route = getattr(instance, "_old_route", None)

    def _clear():
        cache.delete(f"cms:page:{route}")
        cache.delete(HOMEPAGE_CACHE_KEY)
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
        cache.delete(HOMEPAGE_CACHE_KEY)
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

    def _clear():
        try:
            cache.delete("news:list")
        except Exception:  # noqa: BLE001 - a committed article write must not be reported as failed.
            logger.exception("Unable to invalidate the news list cache")

    transaction.on_commit(_clear)


@receiver(post_save, sender=RouteRedirect)
# noinspection PyUnusedLocal
def schedule_route_redirect_edge_sync(sender, instance, **kwargs):
    """Mark one changed mapping pending and reconcile Amplify after commit."""

    previous_is_active = getattr(instance, "_edge_sync_previous_is_active", None)
    requires_edge_sync = bool(instance.is_active or previous_is_active is True or instance.edge_rule_managed)
    if requires_edge_sync:
        RouteRedirect.objects.filter(pk=instance.pk).update(
            edge_sync_status="pending",
            edge_sync_error="",
        )

    redirect_id = instance.pk
    source_path = instance.source_path

    def _schedule():
        from .services.amplify.amplify_redirects import schedule_amplify_redirect_sync

        try:
            cache.delete(f"cms:page:{source_path}")
        except Exception:  # noqa: BLE001 - edge sync must still be scheduled.
            logger.exception("Unable to invalidate the CMS redirect cache")
        if not requires_edge_sync:
            return
        try:
            schedule_amplify_redirect_sync(redirect_ids=(redirect_id,))
        except Exception as exc:  # noqa: BLE001 - the saved CMS change must remain available.
            logger.exception("Unable to schedule Amplify redirect reconciliation")
            try:
                RouteRedirect.objects.filter(pk=redirect_id).update(
                    edge_sync_status="failed",
                    edge_sync_error=str(exc)[:500],
                )
            except Exception:  # noqa: BLE001 - never fail an already-committed admin save.
                logger.exception("Unable to record the Amplify scheduling failure")

    transaction.on_commit(_schedule)
