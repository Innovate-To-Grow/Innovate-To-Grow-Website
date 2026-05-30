"""Tests for cache invalidation signal handlers (B4 fix)."""

import uuid

from django.core.cache import cache
from django.test import TestCase

from apps.cms.models import CMSBlock, CMSPage, FooterContent, Menu, SiteSettings
from apps.cms.signals import (
    invalidate_cms_block_cache,
    invalidate_cms_page_cache,
    stash_old_cms_route,
)


class CacheInvalidationSignalTests(TestCase):
    """Verify that saving or deleting layout models clears the relevant cache keys.

    Cache invalidation is deferred via ``transaction.on_commit`` so we use
    ``captureOnCommitCallbacks(execute=True)`` to flush the callbacks inside
    the test transaction.
    """

    # noinspection PyPep8Naming,PyMethodMayBeStatic
    def setUp(self):
        cache.clear()

    def test_menu_save_clears_layout_cache(self):
        cache.set("layout:data", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            Menu.objects.create(name="signal-test", display_name="Signal Test")
        self.assertIsNone(cache.get("layout:data"))

    def test_menu_delete_clears_layout_cache(self):
        menu = Menu.objects.create(name="del-test", display_name="Del Test")
        cache.set("layout:data", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            menu.delete()
        self.assertIsNone(cache.get("layout:data"))

    def test_footer_save_clears_layout_cache(self):
        cache.set("layout:data", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            FooterContent.objects.create(name="Footer Signal", slug="footer-signal", is_active=True)
        self.assertIsNone(cache.get("layout:data"))

    def test_site_settings_save_clears_layout_cache(self):
        cache.set("layout:data", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            settings = SiteSettings.load()
            settings.homepage_page = None
            settings.save()
        self.assertIsNone(cache.get("layout:data"))

    def test_cms_page_save_clears_layout_cache(self):
        cache.set("layout:data", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            page = CMSPage.objects.create(
                slug="layout-home",
                route="/layout-home",
                title="Layout Home",
                status="published",
            )
            page.title = "Updated Layout Home"
            page.save()
        self.assertIsNone(cache.get("layout:data"))

    def test_route_change_clears_both_old_and_new_page_caches(self):
        page = CMSPage.objects.create(slug="movable", route="/old-route", title="Movable", status="published")
        cache.set("cms:page:/old-route", {"x": 1})
        cache.set("cms:page:/new-route", {"y": 2})
        with self.captureOnCommitCallbacks(execute=True):
            page.route = "/new-route"
            page.save()
        # Both old and new route caches are cleared after a route change.
        self.assertIsNone(cache.get("cms:page:/old-route"))
        self.assertIsNone(cache.get("cms:page:/new-route"))


class SignalHandlerUnitTests(TestCase):
    """Direct invocation of signal handlers to cover defensive branches."""

    def setUp(self):
        cache.clear()

    def test_stash_old_route_for_new_instance_without_pk(self):
        # A freshly constructed instance with pk forced to None takes the else branch.
        instance = CMSPage(slug="brand-new", route="/brand-new", title="New", status="draft")
        instance.pk = None
        stash_old_cms_route(CMSPage, instance)
        self.assertIsNone(instance._old_route)

    def test_stash_old_route_swallows_lookup_error(self):
        # If the route lookup raises ValueError, the handler swallows it and
        # sets _old_route to None.
        from unittest.mock import patch

        instance = CMSPage.objects.create(slug="bad-pk", route="/bad-pk", title="Bad", status="draft")
        with patch.object(CMSPage.objects, "filter", side_effect=ValueError("boom")):
            stash_old_cms_route(CMSPage, instance)
        self.assertIsNone(instance._old_route)

    def test_block_cache_handler_noops_without_page_id(self):
        block = CMSBlock(block_type="rich_text", sort_order=0, data={})
        block.page_id = None
        # Should return early without scheduling any on_commit callback / raising.
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            invalidate_cms_block_cache(CMSBlock, block)
        self.assertEqual(callbacks, [])

    def test_block_cache_handler_tolerates_missing_page(self):
        block = CMSBlock(block_type="rich_text", sort_order=0, data={})
        block.page_id = uuid.uuid4()  # references a page that does not exist
        # The on_commit callback runs, hits CMSPage.DoesNotExist, and is swallowed.
        with self.captureOnCommitCallbacks(execute=True):
            invalidate_cms_block_cache(CMSBlock, block)
        # No exception means the DoesNotExist branch executed cleanly.

    def test_page_cache_handler_clears_new_route_only_when_unchanged(self):
        page = CMSPage.objects.create(slug="stable", route="/stable", title="Stable", status="published")
        page._old_route = "/stable"  # same as current -> old-route branch skipped
        cache.set("cms:page:/stable", {"v": 1})
        with self.captureOnCommitCallbacks(execute=True):
            invalidate_cms_page_cache(CMSPage, page)
        self.assertIsNone(cache.get("cms:page:/stable"))
