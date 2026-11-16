import json

from django.urls import reverse

from apps.cms.admin.cms.page_admin.editor import save_blocks_from_json
from apps.cms.models import CMSBlock, CMSEmbedWidget
from apps.cms.tests.admin.editor.test_cms_admin import _MessageCollector
from apps.cms.tests.admin.editor.test_cms_page_change_form_render import _CMSPageChangeFormRenderCase


class CMSPageChangeFormRenderTests(_CMSPageChangeFormRenderCase):
    def test_save_blocks_from_json_normalizes_embed_widget_hidden_sections_for_storage(self):
        CMSEmbedWidget.objects.create(
            widget_type="app_route",
            app_route="/schedule",
            slug="schedule-embed",
        )
        request = type(
            "Request",
            (),
            {
                "POST": {
                    "blocks_json": json.dumps(
                        [
                            {
                                "block_type": "embed_widget",
                                "admin_label": "Schedule Embed",
                                "data": {"slug": "schedule-embed", "hide_section_titles": True},
                            }
                        ]
                    )
                }
            },
        )()
        messages = _MessageCollector()

        save_blocks_from_json(request, self.page, messages)

        self.assertEqual(messages.errors, [])
        self.assertEqual(messages.warnings, [])
        block = self.page.blocks.get()
        self.assertEqual(block.data["hidden_sections"], ["section_titles"])
        self.assertTrue(block.data["hide_section_titles"])

    def test_save_blocks_from_json_persists_block_level_schedule_id(self):
        from apps.event.models import CurrentProjectSchedule

        CMSEmbedWidget.objects.create(widget_type="app_route", app_route="/schedule", slug="schedule-embed")
        schedule = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)

        messages = self._save_embed_widget_blocks(
            [
                {
                    "block_type": "embed_widget",
                    "admin_label": "2025 schedule",
                    "data": {"slug": "schedule-embed", "schedule_id": str(schedule.pk).upper()},
                }
            ]
        )

        self.assertEqual(messages.errors, [])
        self.assertEqual(messages.warnings, [])
        block = self.page.blocks.get()
        self.assertEqual(block.data["schedule_id"], str(schedule.pk))

    def test_save_blocks_from_json_drops_the_empty_widget_default_schedule_choice(self):
        CMSEmbedWidget.objects.create(widget_type="app_route", app_route="/schedule", slug="schedule-embed")

        messages = self._save_embed_widget_blocks(
            [{"block_type": "embed_widget", "admin_label": "", "data": {"slug": "schedule-embed", "schedule_id": ""}}]
        )

        self.assertEqual(messages.warnings, [])
        self.assertNotIn("schedule_id", self.page.blocks.get().data)

    def test_save_blocks_from_json_warns_and_skips_unknown_schedule_id(self):
        CMSEmbedWidget.objects.create(widget_type="app_route", app_route="/schedule", slug="schedule-embed")

        messages = self._save_embed_widget_blocks(
            [
                {
                    "block_type": "embed_widget",
                    "admin_label": "",
                    "data": {"slug": "schedule-embed", "schedule_id": "00000000-0000-0000-0000-000000000000"},
                }
            ]
        )

        self.assertEqual(self.page.blocks.count(), 0)
        self.assertTrue(any("No schedule found" in w for w in messages.warnings))

    def test_change_form_does_not_render_embed_widget_section(self):
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        content = response.content.decode()
        self.assertNotIn("Embed Widgets on this page", content)
        self.assertNotIn("Manage in Embed Widgets", content)
        changelist_url = reverse("admin:cms_cmsembedwidget_changelist")
        self.assertNotIn(f"{changelist_url}?page__id__exact={self.page.pk}", content)

    def test_change_form_does_not_list_attached_widgets_in_ui(self):
        CMSBlock.objects.create(
            page=self.page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>Hi</p>"},
        )
        widget = CMSEmbedWidget.objects.create(
            page=self.page,
            slug="attached-embed",
            admin_label="Attached Embed",
            block_sort_orders=[0],
        )
        url = reverse("admin:cms_cmspage_change", args=[self.page.pk])
        response = self.client.get(url)
        content = response.content.decode()
        # No dedicated UI section listing widgets...
        self.assertNotIn("Embed Widgets on this page", content)
        self.assertNotIn(
            reverse("admin:cms_cmsembedwidget_change", args=[widget.id]),
            content,
        )
        # ...but the slug is exposed via window.CMS_EMBED_WIDGETS for the block editor picker.
        self.assertIn("CMS_EMBED_WIDGETS", content)
        self.assertIn(widget.slug, content)

    def test_change_form_exposes_schedules_to_the_block_editor(self):
        from apps.event.models import CurrentProjectSchedule

        CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026")
        response = self.client.get(reverse("admin:cms_cmspage_add"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("window.CMS_SCHEDULES", content)
        self.assertIn("Innovate to Grow 2026", content)
