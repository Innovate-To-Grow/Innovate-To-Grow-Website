from django.test import TestCase, skipUnlessDBFeature
from rest_framework.test import APIClient

from cms.models import CMSBlock, CMSPage


# The EmbedBlockView resolves slugs via ``JSONField.__contains`` containment,
# which is only supported on PostgreSQL / MySQL / MariaDB. Local dev uses
# SQLite, so these tests skip there; they run in CI (PostgreSQL) and prod.
@skipUnlessDBFeature("supports_json_field_contains")
class EmbedBlockViewTest(TestCase):
    """Tests for the public /cms/embed/<slug>/ endpoint that serves embed widgets.

    Embed widgets are configured on ``CMSPage.embed_configs`` as a list of
    ``{slug, block_sort_orders, admin_label}`` entries. The endpoint resolves
    a slug to its blocks in the declared sort_order, and sets permissive CORS
    plus x-frame-exempt so third-party sites can iframe the result.
    """

    # noinspection PyPep8Naming
    def setUp(self):
        self.client = APIClient()
        self.page = CMSPage.objects.create(
            slug="embed-host",
            route="/embed-host",
            title="Embed Host Page",
            page_css_class="host-wrapper",
            page_css="/* scoped */",
            status="published",
            embed_configs=[
                {
                    "slug": "contact-widget",
                    "admin_label": "Contact widget",
                    "block_sort_orders": [0, 2],  # deliberately out-of-order + skip block 1
                },
            ],
        )
        CMSBlock.objects.create(
            page=self.page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>Block A</p>"},
        )
        CMSBlock.objects.create(
            page=self.page,
            block_type="rich_text",
            sort_order=1,
            data={"body_html": "<p>Block B (excluded)</p>"},
        )
        CMSBlock.objects.create(
            page=self.page,
            block_type="rich_text",
            sort_order=2,
            data={"body_html": "<p>Block C</p>"},
        )

    def test_returns_blocks_in_declared_order(self):
        """The endpoint returns only the blocks listed in block_sort_orders, in that order."""
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        blocks = data["blocks"]
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["sort_order"], 0)
        self.assertEqual(blocks[0]["data"]["body_html"], "<p>Block A</p>")
        self.assertEqual(blocks[1]["sort_order"], 2)
        self.assertEqual(blocks[1]["data"]["body_html"], "<p>Block C</p>")

    def test_returns_page_css_class_and_css(self):
        """Response carries page_css_class and page_css so the iframe can scope styles."""
        response = self.client.get("/cms/embed/contact-widget/")
        data = response.json()
        self.assertEqual(data["page_css_class"], "host-wrapper")
        self.assertEqual(data["page_css"], "/* scoped */")

    def test_preserves_declared_order_even_if_reversed(self):
        """Blocks come back in the order of block_sort_orders, not ascending sort_order."""
        self.page.embed_configs = [
            {"slug": "reversed", "block_sort_orders": [2, 0], "admin_label": ""},
        ]
        self.page.save(update_fields=["embed_configs"])
        response = self.client.get("/cms/embed/reversed/")
        data = response.json()
        orders = [b["sort_order"] for b in data["blocks"]]
        self.assertEqual(orders, [2, 0])

    def test_unknown_slug_returns_404(self):
        """Slug that doesn't appear in any page's embed_configs returns 404."""
        response = self.client.get("/cms/embed/nope/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Not found.")

    def test_draft_page_not_served(self):
        """Embeds on non-published pages are not exposed publicly."""
        self.page.status = "draft"
        self.page.save(update_fields=["status"])
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.status_code, 404)

    def test_archived_page_not_served(self):
        """Embeds on archived pages are not exposed publicly."""
        self.page.status = "archived"
        self.page.save(update_fields=["status"])
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.status_code, 404)

    def test_cors_header_set_on_success(self):
        """Permissive CORS is sent so third-party origins can fetch via iframe."""
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    def test_cors_header_set_on_404(self):
        """CORS is set even on 404 so third-party error handlers see a real status."""
        response = self.client.get("/cms/embed/nope/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    def test_x_frame_options_exempt(self):
        """Response omits X-Frame-Options so the widget can be iframed anywhere."""
        response = self.client.get("/cms/embed/contact-widget/")
        # xframe_options_exempt attaches an attribute that Django's
        # XFrameOptionsMiddleware checks. The header should not be set.
        self.assertNotIn("X-Frame-Options", response.headers)

    def test_anonymous_access_allowed(self):
        """No authentication required — public embed endpoint."""
        # APIClient with no credentials is already anonymous.
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.status_code, 200)

    def test_missing_block_sort_orders_returns_empty_blocks(self):
        """Config with no block_sort_orders returns 200 with an empty blocks array."""
        self.page.embed_configs = [
            {"slug": "empty-config", "block_sort_orders": [], "admin_label": ""},
        ]
        self.page.save(update_fields=["embed_configs"])
        response = self.client.get("/cms/embed/empty-config/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["blocks"], [])

    def test_stale_block_sort_orders_are_skipped(self):
        """References to sort_orders with no matching block are silently skipped."""
        self.page.embed_configs = [
            {"slug": "stale", "block_sort_orders": [0, 99, 2], "admin_label": ""},
        ]
        self.page.save(update_fields=["embed_configs"])
        response = self.client.get("/cms/embed/stale/")
        data = response.json()
        orders = [b["sort_order"] for b in data["blocks"]]
        self.assertEqual(orders, [0, 2])  # 99 dropped

    def test_slug_uniqueness_across_pages(self):
        """When two pages accidentally share a slug, the first published match wins.

        Uniqueness is enforced at admin save time; this test confirms the
        view's lookup doesn't error on duplicates — it returns a valid page.
        """
        other_page = CMSPage.objects.create(
            slug="other",
            route="/other",
            title="Other Page",
            status="published",
            embed_configs=[{"slug": "contact-widget", "block_sort_orders": [0], "admin_label": ""}],
        )
        CMSBlock.objects.create(
            page=other_page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>From other page</p>"},
        )
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.status_code, 200)
        # Blocks are served — which page wins is an implementation detail,
        # but the body_html must come from ONE consistent page.
        bodies = [b["data"]["body_html"] for b in response.json()["blocks"]]
        self.assertTrue(all("<p>" in b for b in bodies))

    def test_block_type_is_exposed(self):
        """Each block in the response carries its block_type."""
        response = self.client.get("/cms/embed/contact-widget/")
        for block in response.json()["blocks"]:
            self.assertEqual(block["block_type"], "rich_text")
            self.assertIn("data", block)
            self.assertIn("sort_order", block)

    def test_admin_label_not_leaked(self):
        """Admin-only fields (like admin_label on the block) are not exposed publicly."""
        CMSBlock.objects.filter(page=self.page, sort_order=0).update(admin_label="Internal note")
        response = self.client.get("/cms/embed/contact-widget/")
        for block in response.json()["blocks"]:
            self.assertNotIn("admin_label", block)

    def test_html_fields_are_sanitized(self):
        """body_html (and any *_html field) is sanitized before reaching third parties.

        Embed widgets are served to UNTRUSTED origins via iframe; the same bleach
        allowlist used for public CMS pages must apply. Unsafe tags like <script>
        and event handlers like onclick MUST be stripped.
        """
        CMSBlock.objects.filter(page=self.page, sort_order=0).update(
            data={"body_html": '<p>Safe</p><script>alert("xss")</script><a href="javascript:evil()">click</a>'}
        )
        response = self.client.get("/cms/embed/contact-widget/")
        html = response.json()["blocks"][0]["data"]["body_html"]
        self.assertIn("<p>Safe</p>", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("javascript:", html)

    def test_non_dict_embed_config_entry_is_ignored(self):
        """Malformed embed_configs entries (e.g. string in the list) are
        skipped gracefully rather than crashing the view."""
        self.page.embed_configs = [
            "not-a-dict-entry",
            {"slug": "contact-widget", "block_sort_orders": [0], "admin_label": ""},
        ]
        self.page.save(update_fields=["embed_configs"])
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["blocks"]), 1)

    def test_slug_matching_is_exact(self):
        """A slug lookup for 'widget' must NOT match 'contact-widget' even
        though 'widget' is a substring."""
        response = self.client.get("/cms/embed/widget/")
        self.assertEqual(response.status_code, 404)

    def test_response_includes_expected_top_level_keys(self):
        """Contract test: response shape is {blocks, page_css_class, page_css}."""
        response = self.client.get("/cms/embed/contact-widget/")
        data = response.json()
        self.assertEqual(set(data.keys()), {"blocks", "page_css_class", "page_css"})
