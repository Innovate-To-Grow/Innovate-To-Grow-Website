"""Extended signal tests: block changes, route changes, news cache, soft-delete signals."""

from django.core.cache import cache
from django.test import TestCase

from cms.models import CMSBlock, CMSPage, NewsArticle


class CMSBlockCacheInvalidationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.page = CMSPage.objects.create(slug="sig-page", route="/sig-page", title="Signal Page", status="published")

    def test_block_save_clears_page_cache(self):
        cache.set(f"cms:page:{self.page.route}", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            CMSBlock.objects.create(page=self.page, block_type="hero", sort_order=0, data={})
        self.assertIsNone(cache.get(f"cms:page:{self.page.route}"))

    def test_block_delete_clears_page_cache(self):
        block = CMSBlock.objects.create(page=self.page, block_type="hero", sort_order=0, data={})
        cache.set(f"cms:page:{self.page.route}", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            block.delete()
        self.assertIsNone(cache.get(f"cms:page:{self.page.route}"))

    def test_block_update_clears_page_cache(self):
        block = CMSBlock.objects.create(page=self.page, block_type="hero", sort_order=0, data={})
        cache.set(f"cms:page:{self.page.route}", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            block.data = {"heading": "Updated"}
            block.save()
        self.assertIsNone(cache.get(f"cms:page:{self.page.route}"))


class CMSPageRouteChangeCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_route_change_clears_old_and_new_cache(self):
        page = CMSPage.objects.create(slug="moving", route="/old-route", title="Moving Page", status="published")
        cache.set("cms:page:/old-route", {"cached": True})

        with self.captureOnCommitCallbacks(execute=True):
            page.route = "/new-route"
            page.save()

        self.assertIsNone(cache.get("cms:page:/old-route"))
        self.assertIsNone(cache.get("cms:page:/new-route"))

    def test_save_without_route_change_clears_current_route(self):
        page = CMSPage.objects.create(slug="stable", route="/stable", title="Stable", status="published")
        cache.set("cms:page:/stable", {"cached": True})

        with self.captureOnCommitCallbacks(execute=True):
            page.title = "Updated Stable"
            page.save()

        self.assertIsNone(cache.get("cms:page:/stable"))

    def test_page_save_also_clears_layout_cache(self):
        cache.set("layout:data", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            CMSPage.objects.create(slug="layout-clear", route="/layout-clear", title="LC", status="published")
        self.assertIsNone(cache.get("layout:data"))


class NewsArticleCacheInvalidationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_article_save_clears_news_list_cache(self):
        cache.set("news:list", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            from django.utils import timezone

            NewsArticle.objects.create(
                source_guid="cache-test",
                title="Cache Test",
                source_url="https://example.com",
                published_at=timezone.now(),
            )
        self.assertIsNone(cache.get("news:list"))

    def test_article_delete_clears_news_list_cache(self):
        from django.utils import timezone

        article = NewsArticle.objects.create(
            source_guid="del-cache", title="Delete Cache", source_url="https://example.com", published_at=timezone.now()
        )
        cache.set("news:list", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            article.delete()
        self.assertIsNone(cache.get("news:list"))
