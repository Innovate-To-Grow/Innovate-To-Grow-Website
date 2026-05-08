from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from cms.models import CMSBlock, CMSEmbedWidget, CMSPage


class EmbedBlockViewTest(TestCase):
    """Tests for the public /cms/embed/<slug>/ endpoint that serves embed widgets.

    Widgets are stored as ``CMSEmbedWidget`` rows (FK to CMSPage). The endpoint
    resolves a slug to its blocks in the declared ``block_sort_orders``, sets
    permissive CORS, and is x-frame-exempt so third-party sites can iframe the
    result.
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
        self.widget = CMSEmbedWidget.objects.create(
            page=self.page,
            slug="contact-widget",
            admin_label="Contact widget",
            block_sort_orders=[0, 2],
        )

    def test_returns_blocks_in_declared_order(self):
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
        response = self.client.get("/cms/embed/contact-widget/")
        data = response.json()
        self.assertEqual(data["page_css_class"], "host-wrapper")
        self.assertEqual(data["page_css"], "/* scoped */")

    def test_preserves_declared_order_even_if_reversed(self):
        self.widget.block_sort_orders = [2, 0]
        self.widget.save(update_fields=["block_sort_orders"])
        response = self.client.get("/cms/embed/contact-widget/")
        data = response.json()
        orders = [b["sort_order"] for b in data["blocks"]]
        self.assertEqual(orders, [2, 0])

    def test_unknown_slug_returns_404(self):
        response = self.client.get("/cms/embed/nope/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Not found.")

    def test_draft_page_not_served(self):
        self.page.status = "draft"
        self.page.save(update_fields=["status"])
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.status_code, 404)

    def test_archived_page_not_served(self):
        self.page.status = "archived"
        self.page.save(update_fields=["status"])
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.status_code, 404)

    def test_cors_header_set_on_success(self):
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    def test_cors_header_set_on_404(self):
        response = self.client.get("/cms/embed/nope/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    def test_x_frame_options_exempt(self):
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertNotIn("X-Frame-Options", response.headers)

    def test_anonymous_access_allowed(self):
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.status_code, 200)

    def test_missing_block_sort_orders_returns_empty_blocks(self):
        self.widget.block_sort_orders = []
        self.widget.save(update_fields=["block_sort_orders"])
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["blocks"], [])

    def test_stale_block_sort_orders_are_skipped(self):
        self.widget.block_sort_orders = [0, 99, 2]
        self.widget.save(update_fields=["block_sort_orders"])
        response = self.client.get("/cms/embed/contact-widget/")
        data = response.json()
        orders = [b["sort_order"] for b in data["blocks"]]
        self.assertEqual(orders, [0, 2])

    def test_slug_is_globally_unique(self):
        other_page = CMSPage.objects.create(
            slug="other",
            route="/other",
            title="Other Page",
            status="published",
        )
        CMSBlock.objects.create(page=other_page, block_type="rich_text", sort_order=0, data={})
        with self.assertRaises(IntegrityError):
            CMSEmbedWidget.objects.create(
                page=other_page,
                slug="contact-widget",
                block_sort_orders=[0],
            )

    def test_block_type_is_exposed(self):
        response = self.client.get("/cms/embed/contact-widget/")
        for block in response.json()["blocks"]:
            self.assertEqual(block["block_type"], "rich_text")
            self.assertIn("data", block)
            self.assertIn("sort_order", block)

    def test_admin_label_not_leaked(self):
        CMSBlock.objects.filter(page=self.page, sort_order=0).update(admin_label="Internal note")
        response = self.client.get("/cms/embed/contact-widget/")
        for block in response.json()["blocks"]:
            self.assertNotIn("admin_label", block)

    def test_html_fields_are_sanitized(self):
        CMSBlock.objects.filter(page=self.page, sort_order=0).update(
            data={"body_html": '<p>Safe</p><script>alert("xss")</script><a href="javascript:evil()">click</a>'}
        )
        response = self.client.get("/cms/embed/contact-widget/")
        html = response.json()["blocks"][0]["data"]["body_html"]
        self.assertIn("<p>Safe</p>", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("javascript:", html)

    def test_slug_matching_is_exact(self):
        response = self.client.get("/cms/embed/widget/")
        self.assertEqual(response.status_code, 404)

    def test_response_includes_expected_top_level_keys(self):
        response = self.client.get("/cms/embed/contact-widget/")
        data = response.json()
        self.assertEqual(
            set(data.keys()),
            {
                "widget_type",
                "app_route",
                "blocks",
                "page_css_class",
                "page_css",
                "hidden_sections",
                "hide_section_titles",
            },
        )

    def test_blocks_widget_reports_widget_type(self):
        response = self.client.get("/cms/embed/contact-widget/")
        data = response.json()
        self.assertEqual(data["widget_type"], "blocks")
        self.assertEqual(data["app_route"], "")

    def test_hide_section_titles_defaults_to_false(self):
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertFalse(response.json()["hide_section_titles"])
        self.assertEqual(response.json()["hidden_sections"], [])

    def test_hide_section_titles_reflects_widget_setting(self):
        self.widget.hide_section_titles = True
        self.widget.save(update_fields=["hide_section_titles"])
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertTrue(response.json()["hide_section_titles"])
        self.assertEqual(response.json()["hidden_sections"], ["section_titles"])

    def test_hidden_sections_reflect_widget_setting(self):
        self.widget.hidden_sections = ["section_titles"]
        self.widget.save(update_fields=["hidden_sections"])
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.json()["hidden_sections"], ["section_titles"])
        self.assertTrue(response.json()["hide_section_titles"])


class EmbedAppRouteWidgetViewTest(TestCase):
    """Tests for widget_type='app_route' — returns an app-route identifier instead of blocks."""

    # noinspection PyPep8Naming
    def setUp(self):
        self.client = APIClient()
        self.widget = CMSEmbedWidget.objects.create(
            widget_type="app_route",
            app_route="/schedule",
            slug="schedule-embed",
            admin_label="Schedule embed",
        )

    def test_returns_app_route_payload(self):
        response = self.client.get("/cms/embed/schedule-embed/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["widget_type"], "app_route")
        self.assertEqual(data["app_route"], "/schedule")
        self.assertEqual(data["blocks"], [])
        self.assertEqual(data["page_css_class"], "")
        self.assertEqual(data["page_css"], "")
        self.assertEqual(data["hidden_sections"], [])

    def test_does_not_require_page(self):
        self.assertIsNone(self.widget.page_id)
        response = self.client.get("/cms/embed/schedule-embed/")
        self.assertEqual(response.status_code, 200)

    def test_cors_header_set(self):
        response = self.client.get("/cms/embed/schedule-embed/")
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    def test_x_frame_options_exempt(self):
        response = self.client.get("/cms/embed/schedule-embed/")
        self.assertNotIn("X-Frame-Options", response.headers)

    def test_missing_app_route_returns_404(self):
        self.widget.app_route = ""
        self.widget.save(update_fields=["app_route"])
        response = self.client.get("/cms/embed/schedule-embed/")
        self.assertEqual(response.status_code, 404)

    def test_non_embeddable_app_route_returns_404(self):
        self.widget.app_route = "/event"
        self.widget.save(update_fields=["app_route"])
        response = self.client.get("/cms/embed/schedule-embed/")
        self.assertEqual(response.status_code, 404)

    def test_hide_section_titles_reflects_widget_setting(self):
        self.widget.hide_section_titles = True
        self.widget.save(update_fields=["hide_section_titles"])
        response = self.client.get("/cms/embed/schedule-embed/")
        self.assertTrue(response.json()["hide_section_titles"])
        self.assertEqual(response.json()["hidden_sections"], ["section_titles"])

    def test_hide_section_titles_defaults_to_false(self):
        response = self.client.get("/cms/embed/schedule-embed/")
        self.assertFalse(response.json()["hide_section_titles"])
        self.assertEqual(response.json()["hidden_sections"], [])

    def test_hidden_sections_reflect_widget_setting(self):
        self.widget.hidden_sections = ["schedule_header", "schedule_projects"]
        self.widget.save(update_fields=["hidden_sections"])
        response = self.client.get("/cms/embed/schedule-embed/")
        self.assertEqual(response.json()["hidden_sections"], ["schedule_header", "schedule_projects"])
        self.assertFalse(response.json()["hide_section_titles"])

    def test_response_contract_stable(self):
        response = self.client.get("/cms/embed/schedule-embed/")
        self.assertEqual(
            set(response.json().keys()),
            {
                "widget_type",
                "app_route",
                "blocks",
                "page_css_class",
                "page_css",
                "hidden_sections",
                "hide_section_titles",
            },
        )
