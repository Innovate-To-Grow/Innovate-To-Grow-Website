"""Tests for CMS block type validation across all 13 block types."""

from importlib import import_module

from django.apps import apps
from django.core.exceptions import ValidationError
from django.test import TestCase

from cms.models import CMSBlock, CMSEmbedAllowedHost, CMSEmbedWidget, CMSPage
from cms.models.content.cms.block_types import BLOCK_SCHEMAS, BLOCK_TYPE_KEYS, validate_block_data
from cms.services.embed_hosts import invalidate_cache as invalidate_embed_host_cache


class ValidateBlockDataTests(TestCase):
    def test_unknown_block_type_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data("nonexistent", {})
        self.assertIn("Unknown block type", str(ctx.exception))

    def test_hero_valid_empty_data(self):
        """Hero has no required fields."""
        validate_block_data("hero", {})

    def test_hero_valid_with_optional_fields(self):
        validate_block_data("hero", {"heading": "Welcome", "subheading": "Hello", "image_url": "/img.jpg"})

    def test_rich_text_requires_body_html(self):
        with self.assertRaises(ValidationError):
            validate_block_data("rich_text", {})

    def test_rich_text_valid(self):
        validate_block_data("rich_text", {"body_html": "<p>Content</p>"})

    def test_faq_list_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("faq_list", {})

    def test_faq_list_valid(self):
        validate_block_data("faq_list", {"items": [{"question": "Q1", "answer": "A1"}]})

    def test_link_list_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("link_list", {})

    def test_cta_group_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("cta_group", {})

    def test_image_text_requires_body_html(self):
        with self.assertRaises(ValidationError):
            validate_block_data("image_text", {})

    def test_image_text_valid(self):
        validate_block_data("image_text", {"body_html": "<p>Text</p>", "image_url": "/img.jpg"})

    def test_notice_requires_body_html(self):
        with self.assertRaises(ValidationError):
            validate_block_data("notice", {})

    def test_contact_info_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("contact_info", {})

    def test_section_group_requires_sections(self):
        with self.assertRaises(ValidationError):
            validate_block_data("section_group", {})

    def test_table_requires_columns_and_rows(self):
        with self.assertRaises(ValidationError):
            validate_block_data("table", {})
        with self.assertRaises(ValidationError):
            validate_block_data("table", {"columns": ["Name"]})

    def test_table_valid(self):
        validate_block_data("table", {"columns": ["Name", "Value"], "rows": [["A", "1"]]})

    def test_numbered_list_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("numbered_list", {})

    def test_proposal_cards_requires_proposals(self):
        with self.assertRaises(ValidationError):
            validate_block_data("proposal_cards", {})

    def test_navigation_grid_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("navigation_grid", {})

    def test_sponsor_year_requires_year_and_sponsors(self):
        with self.assertRaises(ValidationError):
            validate_block_data("sponsor_year", {})
        with self.assertRaises(ValidationError):
            validate_block_data("sponsor_year", {"year": "", "sponsors": []})
        with self.assertRaises(ValidationError):
            validate_block_data("sponsor_year", {"year": "2025", "sponsors": [{}]})

    def test_sponsor_year_valid(self):
        validate_block_data(
            "sponsor_year",
            {
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

    def test_all_block_types_have_schemas(self):
        """Every block type in BLOCK_TYPE_KEYS must have a corresponding schema."""
        for key in BLOCK_TYPE_KEYS:
            self.assertIn(key, BLOCK_SCHEMAS, f"Missing schema for block type '{key}'")


class EmbedBlockValidationTests(TestCase):
    def setUp(self):
        CMSEmbedAllowedHost.objects.all().delete()
        CMSEmbedAllowedHost.objects.create(hostname="docs.google.com")
        CMSEmbedAllowedHost.objects.create(hostname="*.youtube.com")
        invalidate_embed_host_cache()

    def tearDown(self):
        invalidate_embed_host_cache()

    def test_embed_requires_src(self):
        with self.assertRaises(ValidationError):
            validate_block_data("embed", {})

    def test_embed_rejects_non_https(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data("embed", {"src": "http://docs.google.com/forms/d/e/xyz/viewform"})
        self.assertIn("https", str(ctx.exception))

    def test_embed_rejects_disallowed_host(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data("embed", {"src": "https://evil.example.com/widget"})
        self.assertIn("allowlist", str(ctx.exception))

    def test_embed_allows_exact_host(self):
        validate_block_data("embed", {"src": "https://docs.google.com/forms/d/e/xyz/viewform"})

    def test_embed_wildcard_matches_subdomain(self):
        validate_block_data("embed", {"src": "https://www.youtube.com/embed/abc123"})

    def test_embed_wildcard_does_not_match_sibling_domain(self):
        with self.assertRaises(ValidationError):
            validate_block_data("embed", {"src": "https://fakeyoutube.com/embed/abc"})

    def test_embed_bad_aspect_ratio_rejected(self):
        with self.assertRaises(ValidationError):
            validate_block_data(
                "embed",
                {"src": "https://docs.google.com/a", "aspect_ratio": "sixteen-by-nine"},
            )

    def test_embed_invalid_height_rejected(self):
        with self.assertRaises(ValidationError):
            validate_block_data("embed", {"src": "https://docs.google.com/a", "height": "tall"})
        with self.assertRaises(ValidationError):
            validate_block_data("embed", {"src": "https://docs.google.com/a", "height": -10})

    def test_embed_unknown_sandbox_token_rejected(self):
        with self.assertRaises(ValidationError):
            validate_block_data(
                "embed",
                {"src": "https://docs.google.com/a", "sandbox": "allow-scripts allow-top-navigation"},
            )

    def test_embed_accepts_all_valid_optionals(self):
        validate_block_data(
            "embed",
            {
                "src": "https://docs.google.com/forms/d/xyz/viewform",
                "heading": "Sign-up form",
                "title": "RSVP form",
                "aspect_ratio": "16:9",
                "height": 720,
                "sandbox": "allow-scripts allow-same-origin allow-forms",
                "allow": "fullscreen; clipboard-read",
                "allowfullscreen": True,
            },
        )

    def test_embed_height_upper_bound_enforced(self):
        validate_block_data("embed", {"src": "https://docs.google.com/a", "height": 5000})
        with self.assertRaises(ValidationError):
            validate_block_data("embed", {"src": "https://docs.google.com/a", "height": 5001})

    def test_embed_empty_sandbox_falls_back_to_default(self):
        # An empty string in the `sandbox` field means "use frontend default";
        # the validator must treat it as acceptable, not as unknown tokens.
        validate_block_data("embed", {"src": "https://docs.google.com/a", "sandbox": ""})

    def test_embed_whitespace_only_sandbox_normalized_to_empty(self):
        # Whitespace-only input used to pass validation but be rendered as a
        # present-but-empty sandbox attribute (most restrictive policy),
        # silently breaking scripts/forms/popups. Validator must strip and
        # treat it as blank so the frontend falls back to the default.
        data = {"src": "https://docs.google.com/a", "sandbox": "   "}
        validate_block_data("embed", data)
        self.assertEqual(data["sandbox"], "")

    def test_embed_sandbox_leading_trailing_whitespace_trimmed(self):
        data = {"src": "https://docs.google.com/a", "sandbox": "  allow-scripts allow-forms  "}
        validate_block_data("embed", data)
        self.assertEqual(data["sandbox"], "allow-scripts allow-forms")


class EmbedWidgetBlockValidationTests(TestCase):
    def setUp(self):
        CMSEmbedWidget.objects.all().delete()
        self.page = CMSPage.objects.create(
            slug="embed-widget-validation",
            route="/embed-widget-validation",
            title="Embed Widget Validation",
            status="published",
        )
        CMSEmbedWidget.objects.create(
            widget_type="app_route",
            app_route="/schedule",
            slug="schedule-embed",
        )

    def test_embed_widget_requires_slug(self):
        with self.assertRaises(ValidationError):
            validate_block_data("embed_widget", {})
        with self.assertRaises(ValidationError):
            validate_block_data("embed_widget", {"slug": ""})

    def test_embed_widget_requires_existing_slug(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data("embed_widget", {"slug": "nonexistent-widget"})
        self.assertIn("No CMS embed widget", str(ctx.exception))

    def test_embed_widget_accepts_existing_slug(self):
        validate_block_data("embed_widget", {"slug": "schedule-embed"})

    def test_embed_widget_slug_is_lowercased_for_lookup(self):
        validate_block_data("embed_widget", {"slug": "SCHEDULE-EMBED"})

    def test_embed_widget_bad_aspect_ratio_rejected(self):
        with self.assertRaises(ValidationError):
            validate_block_data(
                "embed_widget",
                {"slug": "schedule-embed", "aspect_ratio": "sixteen-by-nine"},
            )

    def test_embed_widget_invalid_height_rejected(self):
        with self.assertRaises(ValidationError):
            validate_block_data("embed_widget", {"slug": "schedule-embed", "height": "tall"})
        with self.assertRaises(ValidationError):
            validate_block_data("embed_widget", {"slug": "schedule-embed", "height": -5})

    def test_embed_widget_rejects_draft_source_page(self):
        # A blocks-type widget pointing at a draft page would 404 at render time
        # via EmbedBlockView's visibility gate, so block validation must reject
        # it up front rather than let the CMS page save a reference that is
        # guaranteed to fail.
        page = CMSPage.objects.create(slug="draft-page", route="/draft", title="Draft", status="draft")
        CMSEmbedWidget.objects.create(widget_type="blocks", page=page, slug="draft-widget", block_sort_orders=[])
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data("embed_widget", {"slug": "draft-widget"})
        self.assertIn("not published", str(ctx.exception))

    def test_embed_widget_rejects_archived_source_page(self):
        page = CMSPage.objects.create(slug="old-page", route="/old", title="Old", status="archived")
        CMSEmbedWidget.objects.create(widget_type="blocks", page=page, slug="old-widget", block_sort_orders=[])
        with self.assertRaises(ValidationError):
            validate_block_data("embed_widget", {"slug": "old-widget"})

    def test_embed_widget_accepts_published_source_page(self):
        page = CMSPage.objects.create(slug="live-page", route="/live", title="Live", status="published")
        CMSEmbedWidget.objects.create(widget_type="blocks", page=page, slug="live-widget", block_sort_orders=[])
        validate_block_data("embed_widget", {"slug": "live-widget"})

    def test_embed_widget_rejects_after_widget_deleted(self):
        # Saving a block with a valid slug succeeds initially...
        validate_block_data("embed_widget", {"slug": "schedule-embed"})
        # ...but once the widget is removed, re-validation fails loudly so
        # editors can't keep referencing a slug that no longer resolves.
        CMSEmbedWidget.objects.filter(slug="schedule-embed").delete()
        with self.assertRaises(ValidationError):
            validate_block_data("embed_widget", {"slug": "schedule-embed"})

    def test_embed_widget_accepts_all_valid_optionals(self):
        data = {
            "slug": "schedule-embed",
            "heading": "Event Schedule",
            "aspect_ratio": "16:9",
            "height": 480,
            "hide_section_titles": True,
        }
        original = dict(data)
        validate_block_data("embed_widget", data)
        self.assertEqual(data, original)

    def test_embed_widget_accepts_route_specific_hidden_sections(self):
        data = {
            "slug": "schedule-embed",
            "hidden_sections": ["schedule_projects", "section_titles"],
        }
        original = {"slug": "schedule-embed", "hidden_sections": ["schedule_projects", "section_titles"]}
        validate_block_data("embed_widget", data)
        self.assertEqual(data, original)

    def test_embed_widget_rejects_route_incompatible_hidden_sections(self):
        CMSEmbedWidget.objects.create(
            widget_type="app_route",
            app_route="/news",
            slug="news-embed",
        )
        with self.assertRaises(ValidationError):
            validate_block_data("embed_widget", {"slug": "news-embed", "hidden_sections": ["schedule_projects"]})

    def test_embed_widget_hidden_sections_are_authoritative_over_legacy_flag(self):
        data = {"slug": "schedule-embed", "hidden_sections": [], "hide_section_titles": True}
        original = dict(data)
        validate_block_data("embed_widget", data)
        self.assertEqual(data, original)

    def test_embed_widget_clean_normalizes_legacy_hidden_section_flag_for_storage(self):
        block = CMSBlock(
            page=self.page,
            block_type="embed_widget",
            sort_order=0,
            data={"slug": "schedule-embed", "hide_section_titles": True},
        )

        block.full_clean()

        self.assertEqual(block.data["hidden_sections"], ["section_titles"])
        self.assertTrue(block.data["hide_section_titles"])

    def test_embed_widget_clean_normalizes_route_specific_hidden_sections_for_storage(self):
        block = CMSBlock(
            page=self.page,
            block_type="embed_widget",
            sort_order=0,
            data={"slug": "schedule-embed", "hidden_sections": ["schedule_projects", "section_titles"]},
        )

        block.full_clean()

        self.assertEqual(block.data["hidden_sections"], ["section_titles", "schedule_projects"])
        self.assertTrue(block.data["hide_section_titles"])

    def test_embed_widget_clean_treats_explicit_hidden_sections_as_authoritative_for_storage(self):
        block = CMSBlock(
            page=self.page,
            block_type="embed_widget",
            sort_order=0,
            data={"slug": "schedule-embed", "hidden_sections": [], "hide_section_titles": True},
        )

        block.full_clean()

        self.assertEqual(block.data["hidden_sections"], [])
        self.assertFalse(block.data["hide_section_titles"])

    def test_embed_widget_hidden_sections_migration_converts_legacy_block_json(self):
        block = CMSBlock.objects.create(
            page=self.page,
            block_type="embed_widget",
            sort_order=0,
            data={"slug": "schedule-embed", "hide_section_titles": True},
        )
        migration = import_module("cms.migrations.0013_cmspage_embed_widget_hidden_sections")
        migration.migrate_embed_widget_hidden_sections(apps, None)
        block.refresh_from_db()
        self.assertEqual(block.data["hidden_sections"], ["section_titles"])

    def test_embed_widget_accepts_aspect_ratio_without_height(self):
        validate_block_data(
            "embed_widget",
            {"slug": "schedule-embed", "aspect_ratio": "4:3"},
        )

    def test_embed_widget_accepts_positive_height_without_aspect_ratio(self):
        validate_block_data(
            "embed_widget",
            {"slug": "schedule-embed", "height": 720},
        )

    def test_embed_widget_height_upper_bound_enforced(self):
        validate_block_data("embed_widget", {"slug": "schedule-embed", "height": 5000})
        with self.assertRaises(ValidationError):
            validate_block_data("embed_widget", {"slug": "schedule-embed", "height": 5001})


class CMSBlockCleanTests(TestCase):
    def setUp(self):
        self.page = CMSPage.objects.create(slug="block-test", route="/block-test", title="Block Test", status="draft")

    def test_block_full_clean_valid(self):
        block = CMSBlock(page=self.page, block_type="hero", sort_order=0, data={"heading": "Hello"})
        block.full_clean()

    def test_block_full_clean_invalid_data(self):
        block = CMSBlock(page=self.page, block_type="rich_text", sort_order=0, data={})
        with self.assertRaises(ValidationError):
            block.full_clean()

    def test_block_str_with_admin_label(self):
        block = CMSBlock(page=self.page, block_type="hero", sort_order=1, admin_label="Main Banner")
        self.assertEqual(str(block), "Main Banner (#1)")

    def test_block_str_without_admin_label(self):
        block = CMSBlock(page=self.page, block_type="hero", sort_order=0)
        self.assertEqual(str(block), "Hero Banner (#0)")

    def test_block_delete_independent_of_page(self):
        b1 = CMSBlock.objects.create(page=self.page, block_type="hero", sort_order=0, data={})
        CMSBlock.objects.create(page=self.page, block_type="rich_text", sort_order=1, data={"body_html": "<p>Hi</p>"})
        self.assertEqual(CMSBlock.objects.filter(page=self.page).count(), 2)

        b1.delete()
        self.assertEqual(CMSBlock.objects.filter(page=self.page).count(), 1)
