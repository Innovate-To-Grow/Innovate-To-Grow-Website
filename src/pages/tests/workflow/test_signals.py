"""Tests for cache invalidation signal handlers (B4 fix)."""

from django.core.cache import cache
from django.test import TestCase

from pages.models import CMSPage, FooterContent, Menu, SiteSettings


class CacheInvalidationSignalTests(TestCase):
    """Verify that saving or deleting layout models clears the relevant cache keys.

    Cache invalidation is deferred via ``transaction.on_commit`` so we use
    ``captureOnCommitCallbacks(execute=True)`` to flush the callbacks inside
    the test transaction.
    """

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
