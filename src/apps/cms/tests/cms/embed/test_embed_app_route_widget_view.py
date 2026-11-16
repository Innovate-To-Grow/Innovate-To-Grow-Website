from django.test import TestCase
from rest_framework.test import APIClient

from apps.cms.models import CMSEmbedWidget
from apps.event.models import CurrentProjectSchedule


class EmbedAppRouteWidgetViewTest(TestCase):
    """Tests for widget_type='app_route' — returns an app-route identifier instead of blocks."""

    # noinspection PyPep8Naming
    def setUp(self):
        self.client = APIClient()
        self.schedule = CurrentProjectSchedule.objects.create(name="Demo Day")
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
        self.assertEqual(data["hidden_sections"], [])
        self.assertIsNone(data["schedule_id"])

    def test_deleting_a_schedule_detaches_block_level_pins_and_the_widget_default(self):
        # Block pins are JSON (no FK), so a schedule delete must clear them the
        # way the widget FK's SET_NULL clears the widget default.
        from django.core.cache import cache

        from apps.cms.models import CMSBlock, CMSPage

        other = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2024", is_active=False)
        self.widget.schedule = self.schedule
        self.widget.save(update_fields=["schedule"])
        page = CMSPage.objects.create(slug="pinned", route="/pinned", title="Pinned", status="published")
        pinned = CMSBlock.objects.create(
            page=page,
            block_type="embed_widget",
            sort_order=0,
            data={"slug": "schedule-embed", "heading": "2026", "schedule_id": str(self.schedule.pk)},
        )
        untouched = CMSBlock.objects.create(
            page=page,
            block_type="embed_widget",
            sort_order=1,
            data={"slug": "schedule-embed", "schedule_id": str(other.pk)},
        )
        cache.set("cms:page:/pinned", {"stale": True}, timeout=300)

        # Cache invalidation is deferred to transaction.on_commit.
        with self.captureOnCommitCallbacks(execute=True):
            self.schedule.delete()

        pinned.refresh_from_db()
        untouched.refresh_from_db()
        self.widget.refresh_from_db()
        self.assertNotIn("schedule_id", pinned.data)
        self.assertEqual(pinned.data["heading"], "2026")
        self.assertEqual(untouched.data["schedule_id"], str(other.pk))
        self.assertIsNone(self.widget.schedule_id)
        self.assertIsNone(cache.get("cms:page:/pinned"))

    def test_returns_schedule_id_for_configured_schedule_widget(self):
        self.widget.schedule = self.schedule
        self.widget.save(update_fields=["schedule"])

        response = self.client.get("/cms/embed/schedule-embed/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schedule_id"], str(self.schedule.pk))

    def test_non_schedule_app_route_does_not_expose_schedule_id(self):
        self.widget.app_route = "/news"
        self.widget.schedule = self.schedule
        self.widget.save(update_fields=["app_route", "schedule"])

        response = self.client.get("/cms/embed/schedule-embed/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["app_route"], "/news")
        self.assertIsNone(response.json()["schedule_id"])

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
                "hidden_sections",
                "hide_section_titles",
                "schedule_id",
            },
        )
