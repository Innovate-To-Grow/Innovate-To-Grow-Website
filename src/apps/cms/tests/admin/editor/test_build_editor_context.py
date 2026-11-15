import json

from django.test import TestCase
from django.urls import reverse

from apps.cms.admin.cms.page_admin.editor import build_editor_context
from apps.cms.models import BLOCK_SCHEMAS, CMSBlock, CMSEmbedAllowedHost, CMSEmbedWidget, CMSPage


class BuildEditorContextTests(TestCase):
    def test_context_for_existing_page_omits_related_widgets(self):
        page = CMSPage.objects.create(
            slug="ctx-existing",
            route="/ctx-existing",
            title="Ctx Existing",
            status="draft",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>Hi</p>"},
        )
        CMSEmbedWidget.objects.create(
            page=page,
            slug="ctx-widget",
            admin_label="Ctx Widget",
            block_sort_orders=[0],
        )
        context = build_editor_context(page)
        self.assertNotIn("related_widgets", context)

    def test_context_for_new_page_omits_related_widgets(self):
        context = build_editor_context()
        self.assertNotIn("related_widgets", context)

    def test_context_injects_embed_allowed_hosts(self):
        CMSEmbedAllowedHost.objects.all().delete()
        CMSEmbedAllowedHost.objects.create(hostname="docs.google.com", is_active=True)
        CMSEmbedAllowedHost.objects.create(hostname="inactive.example.com", is_active=False)
        context = build_editor_context()
        self.assertIn("embed_allowed_hosts_json", context)
        hosts = json.loads(context["embed_allowed_hosts_json"])
        self.assertIn("docs.google.com", hosts)
        self.assertNotIn("inactive.example.com", hosts)

    def test_context_injects_embed_default_sandbox(self):
        context = build_editor_context()
        self.assertIn("embed_default_sandbox", context)
        sandbox = context["embed_default_sandbox"]
        for token in ("allow-scripts", "allow-same-origin", "allow-forms", "allow-popups"):
            self.assertIn(token, sandbox)

    def test_context_injects_embed_widgets_with_labels(self):
        page = CMSPage.objects.create(
            slug="widget-ctx-src",
            route="/widget-ctx-src",
            title="Widget Ctx Source",
            status="published",
        )
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=0, data={"body_html": "<p>x</p>"})
        CMSEmbedWidget.objects.create(
            widget_type="blocks",
            page=page,
            slug="ctx-blocks-widget",
            admin_label="Ctx Blocks Widget",
            block_sort_orders=[0],
        )
        CMSEmbedWidget.objects.create(
            widget_type="app_route",
            app_route="/schedule",
            slug="ctx-route-widget",
        )
        context = build_editor_context()
        self.assertIn("embed_widgets_json", context)
        widgets = json.loads(context["embed_widgets_json"])
        by_slug = {w["slug"]: w for w in widgets}
        self.assertIn("ctx-blocks-widget", by_slug)
        self.assertIn("ctx-route-widget", by_slug)
        self.assertEqual(by_slug["ctx-blocks-widget"]["widget_type"], "blocks")
        self.assertEqual(by_slug["ctx-blocks-widget"]["app_route"], "")
        self.assertEqual(by_slug["ctx-route-widget"]["widget_type"], "app_route")
        self.assertEqual(by_slug["ctx-route-widget"]["app_route"], "/schedule")
        # Blocks-widget label carries admin_label + the source page title.
        self.assertIn("Ctx Blocks Widget", by_slug["ctx-blocks-widget"]["label"])
        self.assertIn("Widget Ctx Source", by_slug["ctx-blocks-widget"]["label"])
        # App-route widget label exposes the route even without an admin_label.
        self.assertIn("/schedule", by_slug["ctx-route-widget"]["label"])

    def test_context_injects_widget_default_schedule(self):
        from apps.event.models import CurrentProjectSchedule

        schedule = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026")
        CMSEmbedWidget.objects.create(
            widget_type="app_route",
            app_route="/schedule",
            slug="ctx-schedule-widget",
            schedule=schedule,
        )
        CMSEmbedWidget.objects.create(widget_type="app_route", app_route="/schedule", slug="ctx-bare-widget")
        CMSEmbedWidget.objects.create(widget_type="app_route", app_route="/news", slug="ctx-news-widget")
        context = build_editor_context()
        by_slug = {w["slug"]: w for w in json.loads(context["embed_widgets_json"])}
        self.assertEqual(by_slug["ctx-schedule-widget"]["schedule_id"], str(schedule.pk))
        self.assertTrue(by_slug["ctx-schedule-widget"]["supports_schedule"])
        self.assertEqual(by_slug["ctx-bare-widget"]["schedule_id"], "")
        self.assertTrue(by_slug["ctx-bare-widget"]["supports_schedule"])
        self.assertFalse(by_slug["ctx-news-widget"]["supports_schedule"])
        self.assertEqual(by_slug["ctx-news-widget"]["schedule_id"], "")

    def test_context_injects_schedules_active_first(self):
        from apps.event.models import CurrentProjectSchedule

        older = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2024", is_active=False)
        active = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026")
        newer_inactive = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        unnamed = CurrentProjectSchedule.objects.create(name="", is_active=False)
        context = build_editor_context()
        self.assertIn("schedules_json", context)
        schedules = json.loads(context["schedules_json"])
        self.assertEqual(
            [entry["id"] for entry in schedules],
            [str(active.pk), str(unnamed.pk), str(newer_inactive.pk), str(older.pk)],
        )
        self.assertEqual(schedules[0], {"id": str(active.pk), "name": "Innovate to Grow 2026", "is_active": True})
        self.assertEqual(schedules[1]["name"], "Not configured")
        self.assertFalse(schedules[1]["is_active"])

    def test_context_injects_hidden_section_presets(self):
        context = build_editor_context()
        self.assertIn("hidden_section_presets_json", context)
        presets = json.loads(context["hidden_section_presets_json"])
        by_key = {preset["key"]: preset for preset in presets}
        self.assertEqual(by_key["section_titles"]["routes"], [])
        self.assertEqual(by_key["schedule_projects"]["routes"], ["/schedule"])

    def test_context_exposes_embed_widget_block_schema(self):
        context = build_editor_context()
        schemas = json.loads(context["block_schemas_json"])
        self.assertIn("embed_widget", schemas)
        self.assertEqual(schemas["embed_widget"]["required"], ["slug"])
        # Sanity: BLOCK_SCHEMAS itself still matches (guards against silent drift).
        self.assertEqual(schemas["embed_widget"], BLOCK_SCHEMAS["embed_widget"])

    def test_context_injects_asset_manager_config(self):
        context = build_editor_context()
        self.assertIn("asset_manager_config_json", context)
        config = json.loads(context["asset_manager_config_json"])
        self.assertEqual(config["listUrl"], reverse("admin:cms_cmspage_assets"))
        self.assertEqual(config["uploadUrl"], reverse("admin:cms_cmspage_asset_upload"))
        self.assertIn("png", config["imageExtensions"])
        self.assertIn("docx", config["allowedExtensions"])
        self.assertEqual(config["maxBytes"], 20 * 1024 * 1024)
