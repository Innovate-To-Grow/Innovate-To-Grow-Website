from django.test import TestCase

from apps.cms.admin.cms.page_admin.editor import _format_widget_label
from apps.cms.models import CMSBlock, CMSEmbedWidget, CMSPage


class FormatWidgetLabelTests(TestCase):
    """Cover `_format_widget_label` for each widget-type + admin_label variant."""

    def setUp(self):
        self.page = CMSPage.objects.create(
            slug="fmt-src",
            route="/fmt-src",
            title="Fmt Source Page",
            status="draft",
        )
        CMSBlock.objects.create(page=self.page, block_type="rich_text", sort_order=0, data={"body_html": "<p>x</p>"})

    def test_blocks_widget_with_admin_label(self):
        widget = CMSEmbedWidget.objects.create(
            widget_type="blocks",
            page=self.page,
            slug="fmt-blocks-labeled",
            admin_label="My Blocks",
            block_sort_orders=[0],
        )
        label = _format_widget_label(widget)
        self.assertIn("fmt-blocks-labeled", label)
        self.assertIn("My Blocks", label)
        self.assertIn("Fmt Source Page", label)

    def test_blocks_widget_without_admin_label(self):
        widget = CMSEmbedWidget.objects.create(
            widget_type="blocks",
            page=self.page,
            slug="fmt-blocks-bare",
            block_sort_orders=[0],
        )
        label = _format_widget_label(widget)
        self.assertIn("fmt-blocks-bare", label)
        self.assertIn("Fmt Source Page", label)

    def test_app_route_widget_with_admin_label(self):
        widget = CMSEmbedWidget.objects.create(
            widget_type="app_route",
            app_route="/schedule",
            slug="fmt-route-labeled",
            admin_label="Event Schedule",
        )
        label = _format_widget_label(widget)
        self.assertIn("fmt-route-labeled", label)
        self.assertIn("Event Schedule", label)
        self.assertIn("/schedule", label)

    def test_app_route_widget_without_admin_label(self):
        widget = CMSEmbedWidget.objects.create(
            widget_type="app_route",
            app_route="/schedule",
            slug="fmt-route-bare",
        )
        label = _format_widget_label(widget)
        self.assertIn("fmt-route-bare", label)
        self.assertIn("/schedule", label)
