from django.core.cache import cache
from django.test import override_settings

from cms.models import CMSBlock, CMSPage
from core.models.base.system_intelligence import SystemIntelligenceActionRequest
from core.services import system_intelligence_actions as actions

from .base import SystemIntelligenceActionBase


class SystemIntelligenceCMSActionTests(SystemIntelligenceActionBase):
    @override_settings(FRONTEND_URL="http://localhost:5173")
    def test_cms_page_proposal_creates_preview_without_mutating_page(self):
        page = CMSPage.objects.create(slug="about", route="/about", title="About", status="draft")
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=0, data={"body_html": "<p>Old</p>"})

        response = actions.propose_cms_page_update(
            page_id=str(page.pk),
            page_fields={"title": "About Innovate"},
            blocks=[{"block_type": "rich_text", "data": {"body_html": "<p>New</p>"}}],
            summary="Update the About page copy.",
        )

        page.refresh_from_db()
        self.assertEqual(page.title, "About")
        self.assertEqual(page.blocks.get().data, {"body_html": "<p>Old</p>"})
        action = SystemIntelligenceActionRequest.objects.get(id=response["action_request"]["id"])
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_PENDING)
        self.assertIn("cms_preview_token=", action.preview_url)
        self.assertEqual(cache.get(f"cms:preview:{action.preview_token}")["title"], "About Innovate")
        comparison = response["action_request"]["comparison"]
        self.assertEqual(comparison["fields"][0]["field"], "title")
        self.assertEqual(comparison["blocks"][0]["before_text"], "Old")
        self.assertEqual(comparison["blocks"][0]["after_text"], "New")

    @override_settings(FRONTEND_URL="http://localhost:5173")
    def test_approve_cms_page_proposal_applies_page_and_blocks(self):
        page = CMSPage.objects.create(slug="about", route="/about", title="About", status="draft")
        response = actions.propose_cms_page_update(
            page_id=str(page.pk),
            page_fields={"title": "About Innovate"},
            blocks=[{"block_type": "rich_text", "data": {"body_html": "<p>Approved</p>"}}],
        )
        with self.captureOnCommitCallbacks(execute=True):
            action = actions.approve_action_request(response["action_request"]["id"], self.admin_user)
        page.refresh_from_db()
        self.assertEqual(action.status, SystemIntelligenceActionRequest.STATUS_APPLIED)
        self.assertEqual(page.title, "About Innovate")
        self.assertEqual(page.blocks.get().data, {"body_html": "<p>Approved</p>"})
        self.assertIsNone(cache.get(f"cms:preview:{action.preview_token}"))
