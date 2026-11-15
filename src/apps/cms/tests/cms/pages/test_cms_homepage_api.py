from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.cms.models import CMSBlock, CMSPage, SiteSettings
from apps.cms.serializers import CMSPageSerializer


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
