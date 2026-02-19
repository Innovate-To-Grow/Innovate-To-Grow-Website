"""
Tests for Page and HomePage caching behavior.

Covers:
- Page.get_published_by_slug() caching
- HomePage.get_active() caching
- Cache invalidation on save/delete/publish
"""

from django.core.cache import cache
from django.test import TestCase

from ...models import HomePage, Page
from ...models.pages.content.home_page import HOMEPAGE_CACHE_KEY
from ...models.pages.content.page import PAGE_CACHE_KEY_PREFIX


class PageCacheTest(TestCase):
    """Test Page model caching behavior."""

    def setUp(self):
        cache.clear()
        self.page = Page.objects.create(title="Cached Page", slug="cached-page", status="published")

    def tearDown(self):
        cache.clear()

    def test_get_published_by_slug_populates_cache(self):
        """First call populates cache, second call returns cached version."""
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.cached-page"
        self.assertIsNone(cache.get(cache_key))

        result = Page.get_published_by_slug("cached-page")
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.page.pk)

        # Verify it's in cache now
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.pk, self.page.pk)

    def test_get_published_by_slug_returns_none_for_draft(self):
        """Draft page is not returned by get_published_by_slug."""
        Page.objects.create(title="Draft", slug="draft-slug", status="draft")
        self.assertIsNone(Page.get_published_by_slug("draft-slug"))

    def test_get_published_by_slug_returns_none_for_nonexistent(self):
        """Nonexistent slug returns None."""
        self.assertIsNone(Page.get_published_by_slug("nonexistent"))

    def test_save_invalidates_cache(self):
        """Saving a page invalidates its cache entry."""
        # Populate cache
        Page.get_published_by_slug("cached-page")
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.cached-page"
        self.assertIsNotNone(cache.get(cache_key))

        # Save page -> cache invalidated
        self.page.title = "Updated Title"
        self.page.save()
        self.assertIsNone(cache.get(cache_key))

    def test_delete_invalidates_cache(self):
        """Deleting a page invalidates its cache entry."""
        # Populate cache
        Page.get_published_by_slug("cached-page")
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.cached-page"
        self.assertIsNotNone(cache.get(cache_key))

        # Delete page -> cache invalidated
        self.page.delete()
        self.assertIsNone(cache.get(cache_key))

    def test_publish_invalidates_cache(self):
        """Publishing a page invalidates cache (via save)."""
        draft = Page.objects.create(title="Draft", slug="draft-cache", status="draft")
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.draft-cache"

        # Attempt to get (should return None and not cache)
        Page.get_published_by_slug("draft-cache")

        # Publish -> cache cleared
        draft.publish()
        # Now it should be findable
        result = Page.get_published_by_slug("draft-cache")
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, draft.pk)


class HomePageCacheTest(TestCase):
    """Test HomePage caching behavior."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_get_active_populates_cache(self):
        """First call populates cache."""
        hp = HomePage.objects.create(name="Active", status="published", is_active=True)
        self.assertIsNone(cache.get(HOMEPAGE_CACHE_KEY))

        result = HomePage.get_active()
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, hp.pk)

        # Verify cache populated
        cached = cache.get(HOMEPAGE_CACHE_KEY)
        self.assertIsNotNone(cached)

    def test_get_active_returns_none_for_draft(self):
        """Draft home page is not returned by get_active."""
        HomePage.objects.create(name="Draft", status="draft", is_active=False)
        self.assertIsNone(HomePage.get_active())

    def test_save_invalidates_cache(self):
        """Saving a home page invalidates cache."""
        hp = HomePage.objects.create(name="Test", status="published", is_active=True)
        HomePage.get_active()  # Populate cache
        self.assertIsNotNone(cache.get(HOMEPAGE_CACHE_KEY))

        hp.name = "Updated"
        hp.save()
        self.assertIsNone(cache.get(HOMEPAGE_CACHE_KEY))

    def test_delete_invalidates_cache(self):
        """Deleting a home page invalidates cache."""
        hp = HomePage.objects.create(name="Test", status="published", is_active=True)
        HomePage.get_active()  # Populate cache
        self.assertIsNotNone(cache.get(HOMEPAGE_CACHE_KEY))

        hp.delete()
        self.assertIsNone(cache.get(HOMEPAGE_CACHE_KEY))

    def test_unpublish_invalidates_cache(self):
        """Unpublishing clears cache and get_active returns None."""
        hp = HomePage.objects.create(name="Test", status="published", is_active=True)
        HomePage.get_active()  # Populate cache

        hp.unpublish()
        result = HomePage.get_active()
        self.assertIsNone(result)
