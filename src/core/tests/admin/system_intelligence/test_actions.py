from django.core.cache import cache
from django.urls import reverse

from cms.models import CMSBlock, CMSPage, NewsFeedSource
from core.models.base.system_intelligence import SystemIntelligenceActionRequest
from core.services import system_intelligence_actions as actions

from .base import SystemIntelligenceAdminBase


class SystemIntelligenceAdminActionTests(SystemIntelligenceAdminBase):
    def test_action_approve_and_reject_endpoints_update_status_and_data(self):
        source = NewsFeedSource.objects.create(
            name="Feed",
            source_key="feed",
            feed_url="https://example.com/feed.xml",
        )
        approve_action_id = self._propose_update(source, "Approved Feed")
        approve_response = self.client.post(
            reverse("admin:core_system_intelligence_action_approve", args=[approve_action_id])
        )

        self.assertEqual(approve_response.status_code, 200)
        source.refresh_from_db()
        self.assertEqual(source.name, "Approved Feed")
        self.assertEqual(approve_response.json()["action_request"]["status"], "applied")

        reject_action_id = self._propose_update(source, "Rejected Feed")
        reject_response = self.client.post(
            reverse("admin:core_system_intelligence_action_reject", args=[reject_action_id])
        )

        self.assertEqual(reject_response.status_code, 200)
        source.refresh_from_db()
        self.assertEqual(source.name, "Approved Feed")
        self.assertEqual(reject_response.json()["action_request"]["status"], "rejected")

    def test_action_preview_endpoint_renders_cms_payload_inside_admin_frame(self):
        payload = self._propose_cms_update()

        response = self.client.get(
            reverse("admin:core_system_intelligence_action_preview", args=[payload["action_request"]["id"]])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertContains(response, "Previewing changed CMS block content")
        self.assertContains(response, "Updated")
        self.assertContains(response, "New Copy")
        self.assertNotContains(response, "Old")
        self.assertNotContains(response, "Unchanged Hero")

    def test_action_full_preview_endpoint_renders_all_cms_preview_blocks(self):
        payload = self._propose_cms_update()
        action = SystemIntelligenceActionRequest.objects.get(id=payload["action_request"]["id"])

        cached = cache.get(f"cms:preview:{action.preview_token}")
        self.assertIsNotNone(cached)
        response = self.client.get(reverse("admin:core_system_intelligence_action_full_preview", args=[action.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Previewing full proposed CMS page content")
        self.assertContains(response, "Unchanged Hero")
        self.assertContains(response, "Updated")
        self.assertContains(response, "New Copy")
        self.assertNotContains(response, "Old")

    def _propose_update(self, source, name):
        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            payload = actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {"name": name})
        finally:
            actions.reset_action_context(tokens)
        return payload["action_request"]["id"]

    def _propose_cms_update(self):
        page = CMSPage.objects.create(slug="about", route="/about", title="About", status="draft")
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            admin_label="Hero",
            data={"heading": "Hero", "body_html": "<p>Unchanged Hero</p>"},
        )
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=1, data={"body_html": "<p>Old</p>"})

        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            return actions.propose_cms_page_update(
                page_id=str(page.pk),
                blocks=[
                    {
                        "block_type": "rich_text",
                        "admin_label": "Hero",
                        "data": {"heading": "Hero", "body_html": "<p>Unchanged Hero</p>"},
                    },
                    {
                        "block_type": "rich_text",
                        "admin_label": "Intro",
                        "data": {"heading": "Updated", "heading_level": 2, "body_html": "<p>New Copy</p>"},
                    },
                ],
            )
        finally:
            actions.reset_action_context(tokens)
