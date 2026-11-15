"""Tests for the standalone CMSEmbedWidget admin module."""

from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.cms.models import CMSBlock, CMSEmbedWidget, CMSPage
from apps.event.models import CurrentProjectSchedule

Member = get_user_model()


class CMSEmbedWidgetModelTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.page = CMSPage.objects.create(
            slug="host",
            route="/host",
            title="Host",
            status="draft",
        )
        for i in range(3):
            CMSBlock.objects.create(
                page=self.page,
                block_type="rich_text",
                sort_order=i,
                data={"body_html": f"<p>Block {i}</p>"},
            )
        self.schedule = CurrentProjectSchedule.objects.create(name="Demo Day")

    def _full_clean(self, **kwargs):
        widget = CMSEmbedWidget(page=self.page, **kwargs)
        widget.full_clean()
        return widget

    def test_clean_requires_slug(self):
        with self.assertRaises(ValidationError) as ctx:
            self._full_clean(slug="", block_sort_orders=[0])
        self.assertIn("slug", ctx.exception.message_dict)

    def test_clean_rejects_invalid_slug_format(self):
        for bad in ("has space", "-leading", "punct!"):
            with self.assertRaises(ValidationError, msg=f"{bad!r} should fail"):
                self._full_clean(slug=bad, block_sort_orders=[0])

    def test_clean_lowercases_slug(self):
        widget = self._full_clean(slug="Mixed-CASE", block_sort_orders=[0])
        self.assertEqual(widget.slug, "mixed-case")

    def test_clean_requires_valid_block_reference(self):
        with self.assertRaises(ValidationError) as ctx:
            self._full_clean(slug="w1", block_sort_orders=[99])
        self.assertIn("block_sort_orders", ctx.exception.message_dict)

    def test_clean_deduplicates_and_sorts_block_refs(self):
        widget = self._full_clean(slug="w2", block_sort_orders=[2, 0, 2, 1])
        self.assertEqual(widget.block_sort_orders, [0, 1, 2])

    def test_clean_drops_non_integer_refs(self):
        widget = self._full_clean(slug="w3", block_sort_orders=[0, "x", None, 2])
        self.assertEqual(widget.block_sort_orders, [0, 2])

    def test_clean_rejects_no_valid_refs(self):
        with self.assertRaises(ValidationError):
            self._full_clean(slug="w4", block_sort_orders=["nope"])

    def test_app_route_widget_requires_app_route(self):
        widget = CMSEmbedWidget(widget_type="app_route", slug="app-embed")
        with self.assertRaises(ValidationError) as ctx:
            widget.full_clean()
        self.assertIn("app_route", ctx.exception.message_dict)

    def test_app_route_widget_rejects_unknown_route(self):
        widget = CMSEmbedWidget(widget_type="app_route", slug="app-embed", app_route="/nope")
        with self.assertRaises(ValidationError) as ctx:
            widget.full_clean()
        self.assertIn("app_route", ctx.exception.message_dict)

    def test_app_route_widget_rejects_non_embeddable_route(self):
        # /event is in APP_ROUTES (menu/login use it) but not in
        # EMBED_APP_ROUTE_COMPONENTS, so it cannot render in an iframe.
        widget = CMSEmbedWidget(widget_type="app_route", slug="app-embed", app_route="/event")
        with self.assertRaises(ValidationError) as ctx:
            widget.full_clean()
        self.assertIn("app_route", ctx.exception.message_dict)

    def test_app_route_widget_clears_block_sort_orders(self):
        widget = CMSEmbedWidget(
            widget_type="app_route",
            slug="app-embed",
            app_route="/schedule",
            block_sort_orders=[0, 1, 2],
        )
        widget.full_clean()
        self.assertEqual(widget.block_sort_orders, [])
        self.assertEqual(widget.app_route, "/schedule")

    def test_app_route_widget_does_not_require_page(self):
        widget = CMSEmbedWidget(widget_type="app_route", slug="app-embed", app_route="/schedule")
        widget.full_clean()
        self.assertIsNone(widget.page_id)

    def test_schedule_route_widget_keeps_selected_schedule(self):
        widget = CMSEmbedWidget(
            widget_type="app_route",
            slug="schedule-embed",
            app_route="/schedule",
            schedule=self.schedule,
        )
        widget.full_clean()
        self.assertEqual(widget.schedule, self.schedule)

    def test_non_schedule_widget_clears_selected_schedule(self):
        widget = CMSEmbedWidget(
            widget_type="app_route",
            slug="news-embed",
            app_route="/news",
            schedule=self.schedule,
        )
        widget.full_clean()
        self.assertIsNone(widget.schedule)

    def test_blocks_widget_requires_page(self):
        widget = CMSEmbedWidget(widget_type="blocks", slug="bw", block_sort_orders=[0])
        with self.assertRaises(ValidationError) as ctx:
            widget.full_clean()
        self.assertIn("page", ctx.exception.message_dict)

    def test_slug_is_globally_unique_at_db_level(self):
        CMSEmbedWidget.objects.create(page=self.page, slug="shared", block_sort_orders=[0])
        other = CMSPage.objects.create(slug="other", route="/other", title="Other", status="draft")
        CMSBlock.objects.create(page=other, block_type="rich_text", sort_order=0, data={})
        with self.assertRaises(IntegrityError):
            CMSEmbedWidget.objects.create(page=other, slug="shared", block_sort_orders=[0])

    def test_hide_section_titles_default_false(self):
        widget = CMSEmbedWidget.objects.create(page=self.page, slug="default-hide-flag", block_sort_orders=[0])
        widget.refresh_from_db()
        self.assertFalse(widget.hide_section_titles)

    def test_hide_section_titles_roundtrips_when_set_true(self):
        widget = CMSEmbedWidget.objects.create(
            page=self.page,
            slug="enabled-hide-flag",
            block_sort_orders=[0],
            hide_section_titles=True,
        )
        widget.refresh_from_db()
        self.assertTrue(widget.hide_section_titles)

    def test_hidden_sections_default_empty(self):
        widget = CMSEmbedWidget.objects.create(page=self.page, slug="default-hidden-sections", block_sort_orders=[0])
        widget.refresh_from_db()
        self.assertEqual(widget.hidden_sections, [])

    def test_clean_normalizes_hidden_sections_and_legacy_flag(self):
        widget = self._full_clean(slug="hide-section-title", block_sort_orders=[0], hidden_sections=["section_titles"])
        self.assertEqual(widget.hidden_sections, ["section_titles"])
        self.assertTrue(widget.hide_section_titles)

    def test_clean_rejects_route_incompatible_hidden_sections(self):
        with self.assertRaises(ValidationError) as ctx:
            self._full_clean(slug="bad-schedule-hide", block_sort_orders=[0], hidden_sections=["schedule_projects"])
        self.assertIn("hidden_sections", ctx.exception.message_dict)

    def test_app_route_widget_accepts_schedule_hidden_sections(self):
        widget = CMSEmbedWidget(
            widget_type="app_route",
            slug="schedule-sections",
            app_route="/schedule",
            hidden_sections=["schedule_projects", "section_titles"],
        )
        widget.full_clean()
        self.assertEqual(widget.hidden_sections, ["section_titles", "schedule_projects"])

    def test_migration_copies_legacy_hide_title_flag(self):
        widget = CMSEmbedWidget.objects.create(
            page=self.page,
            slug="legacy-title-hide",
            block_sort_orders=[0],
            hide_section_titles=True,
            hidden_sections=[],
        )
        migration = import_module("apps.cms.migrations.0012_cmsembedwidget_hidden_sections")
        migration.migrate_hide_section_titles(apps, None)
        widget.refresh_from_db()
        self.assertEqual(widget.hidden_sections, ["section_titles"])
