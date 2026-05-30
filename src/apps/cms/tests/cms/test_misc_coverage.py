"""Coverage for small leftover branches: asset admin display, host admin deletes,
app config ready(), the cms.urls stub, and a few model __str__ / validation paths."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.cms.admin.cms.cms_asset import CMSAssetAdmin
from apps.cms.admin.cms.cms_embed_allowed_host import CMSEmbedAllowedHostAdmin
from apps.cms.apps import CmsConfig
from apps.cms.models import (
    CMSAsset,
    CMSEmbedAllowedHost,
    CMSEmbedWidget,
    NewsFeedSource,
    PageView,
    StyleSheet,
)
from apps.cms.models.content.cms.block_types.embed import validate_embed_widget_block


class CMSAssetAdminDisplayTests(TestCase):
    def setUp(self):
        self.admin = CMSAssetAdmin(CMSAsset, AdminSite())

    def test_public_url_link_without_file(self):
        self.assertEqual(self.admin.public_url_link(CMSAsset(name="x")), "-")

    def test_file_preview_without_file(self):
        self.assertEqual(self.admin.file_preview(CMSAsset(name="x")), "-")

    def test_file_preview_image_renders_img_tag(self):
        asset = CMSAsset.objects.create(
            name="Logo",
            file=SimpleUploadedFile("logo.png", b"\x89PNG\r\n\x1a\n", content_type="image/png"),
        )
        html = self.admin.file_preview(asset)
        self.assertIn("<img", html)
        self.assertIn(asset.public_url, html)

    def test_file_preview_non_image_renders_open_link(self):
        asset = CMSAsset.objects.create(
            name="Doc",
            file=SimpleUploadedFile("doc.pdf", b"%PDF-1.7\n", content_type="application/pdf"),
        )
        html = self.admin.file_preview(asset)
        self.assertIn("Open file", html)
        self.assertNotIn("<img", html)


class CMSEmbedAllowedHostAdminTests(TestCase):
    def setUp(self):
        self.admin = CMSEmbedAllowedHostAdmin(CMSEmbedAllowedHost, AdminSite())

    def test_delete_queryset_invalidates_host_cache(self):
        CMSEmbedAllowedHost.objects.create(hostname="a.example.com", is_active=True)
        CMSEmbedAllowedHost.objects.create(hostname="b.example.com", is_active=True)
        qs = CMSEmbedAllowedHost.objects.all()

        with patch("apps.cms.admin.cms.cms_embed_allowed_host.invalidate_cache") as mock_invalidate:
            self.admin.delete_queryset(request=None, queryset=qs)
            mock_invalidate.assert_called_once()

        self.assertEqual(CMSEmbedAllowedHost.objects.count(), 0)


class CmsConfigReadyTests(TestCase):
    def test_ready_swallows_import_error(self):
        config = CmsConfig.create("apps.cms")
        # Force the admin import to fail so the defensive except branch executes.
        with patch("builtins.__import__", side_effect=ImportError("boom")):
            # Should not raise despite the import failure.
            config.ready()


class CmsUrlsStubTests(TestCase):
    def test_urls_module_defines_empty_patterns(self):
        from apps.cms import urls

        self.assertEqual(urls.app_name, "cms")
        self.assertEqual(urls.urlpatterns, [])


class ModelStrAndValidationTests(TestCase):
    def test_page_view_str(self):
        pv = PageView(path="/about")
        self.assertIn("/about", str(pv))

    def test_style_sheet_str_prefers_display_name(self):
        self.assertEqual(str(StyleSheet(name="base", display_name="Base Styles")), "Base Styles")

    def test_style_sheet_str_falls_back_to_name(self):
        self.assertEqual(str(StyleSheet(name="base", display_name="")), "base")

    def test_news_feed_source_str(self):
        source = NewsFeedSource(name="UC Merced", source_key="ucm", feed_url="https://x/feed")
        self.assertEqual(str(source), "UC Merced")

    def test_embed_widget_block_app_route_not_configured_raises(self):
        # Create an app_route widget with an unembeddable route, bypassing clean()
        # via direct create, so is_visible() returns False and the app_route
        # branch of validation raises.
        CMSEmbedWidget.objects.create(
            widget_type="app_route",
            slug="broken-route",
            app_route="/not-embeddable",
            block_sort_orders=[],
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_embed_widget_block({"slug": "broken-route"})
        self.assertIn("app route is not configured", str(ctx.exception))

    def test_embed_widget_clean_rejects_non_list_block_sort_orders(self):
        from apps.cms.models import CMSPage

        page = CMSPage.objects.create(slug="wp", route="/wp", title="WP", status="draft")
        widget = CMSEmbedWidget(widget_type="blocks", slug="badrefs", page=page, block_sort_orders="not-a-list")
        with self.assertRaises(ValidationError) as ctx:
            widget.full_clean()
        self.assertIn("block_sort_orders", ctx.exception.message_dict)
