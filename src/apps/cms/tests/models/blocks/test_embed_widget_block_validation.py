from importlib import import_module

from django.apps import apps
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cms.models import CMSBlock, CMSEmbedWidget, CMSPage
from apps.cms.models.content.cms.block_types import (
    validate_block_data,
)


class _EmbedWidgetBlockValidationCase(TestCase):
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


class EmbedWidgetBlockValidationTests(_EmbedWidgetBlockValidationCase):
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
        migration = import_module("apps.cms.migrations.0013_cmspage_embed_widget_hidden_sections")
        migration.migrate_embed_widget_hidden_sections(apps, None)
        block.refresh_from_db()
        self.assertEqual(block.data["hidden_sections"], ["section_titles"])
