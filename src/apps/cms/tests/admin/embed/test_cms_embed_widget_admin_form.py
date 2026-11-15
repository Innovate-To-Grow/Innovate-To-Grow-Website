from django.test import TestCase

from apps.cms.admin.cms.cms_embed_widget import CMSEmbedWidgetAdminForm
from apps.cms.models import CMSBlock, CMSPage
from apps.event.models import CurrentProjectSchedule


class CMSEmbedWidgetAdminFormTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.page = CMSPage.objects.create(slug="host", route="/host", title="Host", status="draft")
        self.schedule = CurrentProjectSchedule.objects.create(name="Demo Day")
        for i in range(2):
            CMSBlock.objects.create(page=self.page, block_type="rich_text", sort_order=i, data={})

    def test_form_valid_with_hidden_block_sort_orders(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "blocks",
                "page": str(self.page.pk),
                "slug": "valid-widget",
                "admin_label": "Valid",
                "block_sort_orders": "[0, 1]",
                "app_route": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        self.assertEqual(widget.slug, "valid-widget")
        self.assertEqual(widget.widget_type, "blocks")
        self.assertEqual(widget.block_sort_orders, [0, 1])

    def test_form_rejects_invalid_slug(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "blocks",
                "page": str(self.page.pk),
                "slug": "Bad Slug",
                "admin_label": "",
                "block_sort_orders": "[0]",
                "app_route": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("slug", form.errors)

    def test_form_valid_for_app_route_widget(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "app_route",
                "page": "",
                "slug": "schedule-embed",
                "admin_label": "Schedule",
                "block_sort_orders": "[]",
                "app_route": "/schedule",
                "schedule": str(self.schedule.pk),
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        self.assertEqual(widget.widget_type, "app_route")
        self.assertEqual(widget.app_route, "/schedule")
        self.assertEqual(widget.schedule, self.schedule)
        self.assertIsNone(widget.page_id)
        self.assertEqual(widget.block_sort_orders, [])

    def test_form_clears_schedule_for_non_schedule_app_route(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "app_route",
                "page": "",
                "slug": "news-embed",
                "admin_label": "News",
                "block_sort_orders": "[]",
                "app_route": "/news",
                "schedule": str(self.schedule.pk),
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        self.assertEqual(widget.app_route, "/news")
        self.assertIsNone(widget.schedule)

    def test_form_clears_schedule_for_blocks_widget(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "blocks",
                "page": str(self.page.pk),
                "slug": "blocks-embed",
                "admin_label": "Blocks",
                "block_sort_orders": "[0]",
                "app_route": "",
                "schedule": str(self.schedule.pk),
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        self.assertEqual(widget.widget_type, "blocks")
        self.assertIsNone(widget.schedule)

    def test_form_rejects_app_route_widget_with_unknown_route(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "app_route",
                "page": "",
                "slug": "app-embed",
                "admin_label": "",
                "block_sort_orders": "[]",
                "app_route": "/unknown",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("app_route", form.errors)

    def test_form_persists_hidden_sections(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "blocks",
                "page": str(self.page.pk),
                "slug": "hide-sections-on",
                "admin_label": "",
                "block_sort_orders": "[0]",
                "app_route": "",
                "hidden_sections": ["section_titles"],
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        widget.refresh_from_db()
        self.assertEqual(widget.hidden_sections, ["section_titles"])
        self.assertTrue(widget.hide_section_titles)

    def test_form_persists_route_specific_hidden_sections(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "app_route",
                "page": "",
                "slug": "schedule-hidden-sections",
                "admin_label": "",
                "block_sort_orders": "[]",
                "app_route": "/schedule",
                "hidden_sections": ["schedule_header", "schedule_projects"],
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        widget.refresh_from_db()
        self.assertEqual(widget.hidden_sections, ["schedule_header", "schedule_projects"])
        self.assertFalse(widget.hide_section_titles)

    def test_form_rejects_route_incompatible_hidden_sections(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "app_route",
                "page": "",
                "slug": "news-hidden-sections",
                "admin_label": "",
                "block_sort_orders": "[]",
                "app_route": "/news",
                "hidden_sections": ["schedule_projects"],
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("hidden_sections", form.errors)

    def test_form_defaults_hidden_sections_empty_when_omitted(self):
        form = CMSEmbedWidgetAdminForm(
            data={
                "widget_type": "blocks",
                "page": str(self.page.pk),
                "slug": "hide-sections-off",
                "admin_label": "",
                "block_sort_orders": "[0]",
                "app_route": "",
                # hidden_sections intentionally omitted — no checkbox selected
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        widget = form.save()
        widget.refresh_from_db()
        self.assertEqual(widget.hidden_sections, [])
        self.assertFalse(widget.hide_section_titles)
