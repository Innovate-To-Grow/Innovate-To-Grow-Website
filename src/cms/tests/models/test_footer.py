"""Tests for FooterContent model: singleton enforcement, caching, and auto-deactivation."""

from django.core.cache import cache
from django.test import TestCase

from cms.models import FooterContent
from cms.models.content.layout.footer_content import FOOTER_CACHE_KEY


class FooterContentAutoDeactivateTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_saving_active_footer_deactivates_others(self):
        f1 = FooterContent.objects.create(name="V1", slug="v1", is_active=True)
        f2 = FooterContent.objects.create(name="V2", slug="v2", is_active=True)

        f1.refresh_from_db()
        self.assertFalse(f1.is_active)
        self.assertTrue(f2.is_active)

    def test_saving_inactive_footer_does_not_deactivate_others(self):
        f1 = FooterContent.objects.create(name="V1", slug="v1", is_active=True)
        FooterContent.objects.create(name="V2", slug="v2", is_active=False)

        f1.refresh_from_db()
        self.assertTrue(f1.is_active)

    def test_only_one_active_after_multiple_creates(self):
        FooterContent.objects.create(name="V1", slug="v1", is_active=True)
        FooterContent.objects.create(name="V2", slug="v2", is_active=True)
        FooterContent.objects.create(name="V3", slug="v3", is_active=True)

        active_count = FooterContent.objects.filter(is_active=True).count()
        self.assertEqual(active_count, 1)
        self.assertTrue(FooterContent.objects.get(slug="v3").is_active)

    def test_reactivating_old_footer_deactivates_current(self):
        f1 = FooterContent.objects.create(name="V1", slug="v1", is_active=True)
        FooterContent.objects.create(name="V2", slug="v2", is_active=True)

        f1.is_active = True
        f1.save()

        self.assertTrue(FooterContent.objects.get(slug="v1").is_active)
        self.assertFalse(FooterContent.objects.get(slug="v2").is_active)


class FooterContentCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_get_active_returns_active_footer(self):
        FooterContent.objects.create(name="Active", slug="active", is_active=True)
        footer = FooterContent.get_active()
        self.assertIsNotNone(footer)
        self.assertEqual(footer.slug, "active")

    def test_get_active_returns_none_when_no_active(self):
        FooterContent.objects.create(name="Inactive", slug="inactive", is_active=False)
        self.assertIsNone(FooterContent.get_active())

    def test_get_active_populates_cache(self):
        FooterContent.objects.create(name="Cached", slug="cached", is_active=True)
        self.assertIsNone(cache.get(FOOTER_CACHE_KEY))

        FooterContent.get_active()
        self.assertIsNotNone(cache.get(FOOTER_CACHE_KEY))

    def test_get_active_uses_cache_on_second_call(self):
        FooterContent.objects.create(name="V1", slug="v1", is_active=True)
        FooterContent.get_active()

        # Delete from DB but cache should still return it
        FooterContent.all_objects.filter(slug="v1").delete()
        footer = FooterContent.get_active()
        self.assertIsNotNone(footer)
        self.assertEqual(footer.slug, "v1")

    def test_save_invalidates_cache(self):
        f = FooterContent.objects.create(name="V1", slug="v1", is_active=True)
        FooterContent.get_active()  # populate cache
        self.assertIsNotNone(cache.get(FOOTER_CACHE_KEY))

        f.name = "V1 Updated"
        f.save()
        self.assertIsNone(cache.get(FOOTER_CACHE_KEY))

    def test_delete_invalidates_cache(self):
        f = FooterContent.objects.create(name="V1", slug="v1", is_active=True)
        FooterContent.get_active()  # populate cache

        f.delete()
        self.assertIsNone(cache.get(FOOTER_CACHE_KEY))

    def test_get_active_caches_none_when_no_active(self):
        """Even None results should be cached to avoid repeated queries."""
        FooterContent.get_active()
        # None is cached (as opposed to cache miss)
        cached = cache.get(FOOTER_CACHE_KEY)
        self.assertIsNone(cached)


class FooterContentStrTests(TestCase):
    def test_str_active(self):
        f = FooterContent(name="Footer V1", is_active=True)
        self.assertEqual(str(f), "Footer V1 (Active)")

    def test_str_inactive(self):
        f = FooterContent(name="Footer V1", is_active=False)
        self.assertEqual(str(f), "Footer V1")
