"""Tests for CMS page views: preview mode, caching, 404s, and permission checks."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from cms.models import CMSBlock, CMSPage

User = get_user_model()


def _make_page(slug, route, status="published", **kwargs):
    return CMSPage.objects.create(slug=slug, route=route, title=kwargs.pop("title", slug.title()), status=status, **kwargs)


class CMSPageViewPublicTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_published_page_returned(self):
        _make_page("about", "/about")
        resp = self.client.get("/cms/pages/about/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["slug"], "about")

    def test_draft_page_returns_404(self):
        _make_page("draft", "/draft", status="draft")
        resp = self.client.get("/cms/pages/draft/")
        self.assertEqual(resp.status_code, 404)

    def test_archived_page_returns_404(self):
        _make_page("old", "/old", status="archived")
        resp = self.client.get("/cms/pages/old/")
        self.assertEqual(resp.status_code, 404)

    def test_nonexistent_route_returns_404(self):
        resp = self.client.get("/cms/pages/nope/")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"], "Page not found.")

    def test_root_page(self):
        _make_page("home", "/")
        resp = self.client.get("/cms/pages/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["route"], "/")

    def test_nested_route(self):
        _make_page("deep", "/about/team/leads")
        resp = self.client.get("/cms/pages/about/team/leads/")
        self.assertEqual(resp.status_code, 200)

    def test_response_includes_blocks(self):
        page = _make_page("with-blocks", "/with-blocks")
        CMSBlock.objects.create(page=page, block_type="hero", sort_order=0, data={})
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=1, data={"body_html": "<p>Hi</p>"})

        resp = self.client.get("/cms/pages/with-blocks/")
        blocks = resp.json()["blocks"]
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["block_type"], "hero")
        self.assertEqual(blocks[1]["block_type"], "rich_text")

    def test_soft_deleted_blocks_excluded(self):
        page = _make_page("del-blocks", "/del-blocks")
        CMSBlock.objects.create(page=page, block_type="hero", sort_order=0, data={})
        deleted_block = CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=1, data={"body_html": "<p>Gone</p>"})
        deleted_block.delete()  # soft delete

        resp = self.client.get("/cms/pages/del-blocks/")
        self.assertEqual(len(resp.json()["blocks"]), 1)

    def test_blocks_ordered_by_sort_order(self):
        page = _make_page("ordered", "/ordered")
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=2, data={"body_html": "<p>Second</p>"})
        CMSBlock.objects.create(page=page, block_type="hero", sort_order=0, data={})

        resp = self.client.get("/cms/pages/ordered/")
        blocks = resp.json()["blocks"]
        self.assertEqual(blocks[0]["block_type"], "hero")
        self.assertEqual(blocks[1]["block_type"], "rich_text")

    def test_no_auth_required(self):
        _make_page("public", "/public")
        resp = self.client.get("/cms/pages/public/")
        self.assertEqual(resp.status_code, 200)


class CMSPageViewCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_response_is_cached(self):
        _make_page("cached", "/cached")
        self.client.get("/cms/pages/cached/")
        self.assertIsNotNone(cache.get("cms:page:/cached"))

    def test_cached_response_served(self):
        cache.set("cms:page:/cached", {"slug": "cached", "from": "cache"})
        resp = self.client.get("/cms/pages/cached/")
        self.assertEqual(resp.json()["from"], "cache")

    def test_root_page_cache_key(self):
        _make_page("home", "/")
        self.client.get("/cms/pages/")
        self.assertIsNotNone(cache.get("cms:page:/"))


class CMSPagePreviewModeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.staff = User.objects.create_user(username="staff", password="pass", is_staff=True)
        self.regular = User.objects.create_user(username="regular", password="pass")

    def test_preview_mode_shows_draft_for_staff(self):
        _make_page("draft-preview", "/draft-preview", status="draft")
        self.client.force_authenticate(self.staff)
        resp = self.client.get("/cms/pages/draft-preview/?preview=true")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["slug"], "draft-preview")

    def test_preview_mode_excludes_archived_for_staff(self):
        _make_page("archived-preview", "/archived-preview", status="archived")
        self.client.force_authenticate(self.staff)
        resp = self.client.get("/cms/pages/archived-preview/?preview=true")
        self.assertEqual(resp.status_code, 404)

    def test_preview_mode_ignored_for_anonymous(self):
        _make_page("anon-preview", "/anon-preview", status="draft")
        resp = self.client.get("/cms/pages/anon-preview/?preview=true")
        self.assertEqual(resp.status_code, 404)

    def test_preview_mode_ignored_for_non_staff(self):
        _make_page("regular-preview", "/regular-preview", status="draft")
        self.client.force_authenticate(self.regular)
        resp = self.client.get("/cms/pages/regular-preview/?preview=true")
        self.assertEqual(resp.status_code, 404)

    def test_preview_mode_does_not_cache(self):
        _make_page("no-cache-preview", "/no-cache-preview", status="draft")
        self.client.force_authenticate(self.staff)
        self.client.get("/cms/pages/no-cache-preview/?preview=true")
        self.assertIsNone(cache.get("cms:page:/no-cache-preview"))

    def test_preview_bypasses_cache(self):
        cache.set("cms:page:/stale", {"slug": "stale", "from": "cache"})
        _make_page("stale", "/stale")
        self.client.force_authenticate(self.staff)
        resp = self.client.get("/cms/pages/stale/?preview=true")
        self.assertNotIn("from", resp.json())


class CMSLivePreviewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.staff = User.objects.create_user(username="staff", password="pass", is_staff=True)
        self.page = _make_page("live", "/live")

    def test_post_requires_staff(self):
        resp = self.client.post(f"/cms/live-preview/{self.page.pk}/", '{"title":"Test"}', content_type="application/json")
        self.assertIn(resp.status_code, (401, 403))

    def test_post_staff_stores_data(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(
            f"/cms/live-preview/{self.page.pk}/",
            '{"title":"Preview Title"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_get_returns_cached_preview(self):
        self.client.force_authenticate(self.staff)
        self.client.post(
            f"/cms/live-preview/{self.page.pk}/",
            '{"title":"Preview"}',
            content_type="application/json",
        )

        resp = self.client.get(f"/cms/live-preview/{self.page.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["title"], "Preview")

    def test_get_no_cache_falls_back_to_db(self):
        resp = self.client.get(f"/cms/live-preview/{self.page.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["slug"], "live")

    def test_get_nonexistent_page_returns_404(self):
        import uuid

        resp = self.client.get(f"/cms/live-preview/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)

    def test_post_invalid_json_returns_400(self):
        self.client.force_authenticate(self.staff)
        resp = self.client.post(
            f"/cms/live-preview/{self.page.pk}/",
            "not json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


class CMSPreviewFetchTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_valid_token_returns_data(self):
        cache.set("cms:preview:test-token-123", {"slug": "preview-page", "title": "Preview"})
        resp = self.client.get("/cms/preview/test-token-123/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["slug"], "preview-page")

    def test_invalid_token_returns_404(self):
        resp = self.client.get("/cms/preview/nonexistent-token/")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())
