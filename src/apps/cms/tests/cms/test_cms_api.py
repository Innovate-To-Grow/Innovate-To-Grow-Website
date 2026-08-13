from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.cms.models import CMSBlock, CMSPage, SiteSettings
from apps.cms.serializers import CMSPageSerializer


class CMSPageAPITest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_get_published_page(self):
        page = CMSPage.objects.create(
            slug="about",
            route="/about",
            title="About",
            page_css_class="about-page",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"heading": "About Us", "body_html": "<p>Hello</p>"},
        )

        response = self.client.get("/cms/pages/about/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["slug"], "about")
        self.assertEqual(data["route"], "/about")
        self.assertEqual(data["title"], "About")
        self.assertEqual(data["page_css_class"], "about-page")
        self.assertEqual(len(data["blocks"]), 1)
        self.assertEqual(data["blocks"][0]["block_type"], "rich_text")
        self.assertEqual(data["blocks"][0]["data"]["heading"], "About Us")

    def test_draft_page_404_for_public(self):
        CMSPage.objects.create(
            slug="draft-page",
            route="/draft-page",
            title="Draft",
            status="draft",
        )
        response = self.client.get("/cms/pages/draft-page/")
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_page_404(self):
        response = self.client.get("/cms/pages/nonexistent/")
        self.assertEqual(response.status_code, 404)

    def test_blocks_ordered_by_sort_order(self):
        page = CMSPage.objects.create(
            slug="ordered",
            route="/ordered",
            title="Ordered",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=2,
            data={"body_html": "<p>Second</p>"},
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>First</p>"},
        )

        response = self.client.get("/cms/pages/ordered/")
        blocks = response.json()["blocks"]
        self.assertEqual(blocks[0]["sort_order"], 0)
        self.assertEqual(blocks[1]["sort_order"], 2)

    def test_soft_deleted_blocks_excluded(self):
        page = CMSPage.objects.create(
            slug="del-block",
            route="/del-block",
            title="Del Block",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>Visible</p>"},
        )
        deleted = CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=1,
            data={"body_html": "<p>Deleted</p>"},
        )
        deleted.delete()  # soft delete

        response = self.client.get("/cms/pages/del-block/")
        self.assertEqual(len(response.json()["blocks"]), 1)

    def test_response_is_cached(self):
        CMSPage.objects.create(
            slug="cached",
            route="/cached",
            title="Cached",
            status="published",
        )

        # First request populates cache
        response1 = self.client.get("/cms/pages/cached/")
        self.assertEqual(response1.status_code, 200)

        # Verify cache hit by checking the cache key exists
        cached = cache.get("cms:page:/cached")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["slug"], "cached")

    def test_published_page_etag_returns_304(self):
        CMSPage.objects.create(slug="etag", route="/etag", title="ETag", status="published")
        first = self.client.get("/cms/pages/etag/")

        second = self.client.get("/cms/pages/etag/", HTTP_IF_NONE_MATCH=first["ETag"])

        self.assertEqual(second.status_code, 304)


class CMSHomepageAPITest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_returns_selected_published_page_with_serializer_parity(self):
        page = CMSPage.objects.create(slug="home", route="/welcome", title="Welcome", status="published")
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=0, data={"body_html": "<p>Hi</p>"})
        settings = SiteSettings.load()
        settings.homepage_page = page
        settings.save()

        response = self.client.get("/cms/homepage/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), CMSPageSerializer(page).data)

    def test_draft_selection_falls_back_to_published_root(self):
        draft = CMSPage.objects.create(slug="draft-home", route="/draft-home", title="Draft", status="draft")
        root = CMSPage.objects.create(slug="root", route="/", title="Root", status="published")
        settings = SiteSettings.load()
        settings.homepage_page = draft
        settings.save()

        response = self.client.get("/cms/homepage/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], root.slug)

    def test_page_and_block_changes_invalidate_cached_homepage(self):
        page = CMSPage.objects.create(slug="home-cache", route="/home-cache", title="Before", status="published")
        settings = SiteSettings.load()
        settings.homepage_page = page
        with self.captureOnCommitCallbacks(execute=True):
            settings.save()
        self.client.get("/cms/homepage/")

        page.title = "After"
        with self.captureOnCommitCallbacks(execute=True):
            page.save()
        self.assertEqual(self.client.get("/cms/homepage/").json()["title"], "After")

        with self.captureOnCommitCallbacks(execute=True):
            CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=0, data={"body_html": "<p>New</p>"})
        self.assertEqual(len(self.client.get("/cms/homepage/").json()["blocks"]), 1)

    def test_preview_response_has_no_public_cache_headers(self):
        page = CMSPage.objects.create(slug="private", route="/private", title="Private", status="draft")
        response = self.client.get("/cms/pages/private/?preview=true")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("ETag", response)
        self.assertNotIn("public", response.get("Cache-Control", ""))

    def test_sponsor_year_block_is_returned(self):
        page = CMSPage.objects.create(
            slug="acknowledgement-api",
            route="/acknowledgement-api",
            title="Partners & Sponsors",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="sponsor_year",
            sort_order=0,
            data={
                "year": "2025",
                "sponsors": [
                    {
                        "name": "Acme Labs",
                        "logo_url": "/media/cms/assets/acme.svg",
                        "website": "https://example.com",
                    }
                ],
            },
        )

        response = self.client.get("/cms/pages/acknowledgement-api/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["blocks"][0]["block_type"], "sponsor_year")
        self.assertEqual(data["blocks"][0]["data"]["year"], "2025")
        self.assertEqual(data["blocks"][0]["data"]["sponsors"][0]["name"], "Acme Labs")
