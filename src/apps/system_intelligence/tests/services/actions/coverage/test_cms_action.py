import json

from apps.cms.models import CMSPage
from apps.system_intelligence.models import SystemIntelligenceActionRequest
from apps.system_intelligence.services import actions
from apps.system_intelligence.services.actions.cms import actions as cms_actions
from apps.system_intelligence.services.actions.context import (
    current_conversation,
    current_user,
    current_user_id,
)
from apps.system_intelligence.services.actions.exceptions import ActionRequestError

from ..support.base import SystemIntelligenceActionBase


# ---------------------------------------------------------------------------
# cms/actions.py
# ---------------------------------------------------------------------------
class CmsActionTests(SystemIntelligenceActionBase):
    def test_get_cms_page_detail_not_found_raises(self):
        with self.assertRaises(ActionRequestError) as cm:
            cms_actions.get_cms_page_detail(slug="missing")
        self.assertIn("CMS page not found", str(cm.exception))

    def test_get_cms_page_detail_returns_serialized_json(self):
        page = CMSPage.objects.create(slug="about", route="/about", title="About", status="draft")
        result = cms_actions.get_cms_page_detail(page_id=str(page.pk))
        payload = json.loads(result)
        self.assertEqual(payload["title"], "About")
        self.assertEqual(payload["slug"], "about")

    def test_apply_cms_page_update_stores_normalized_block_data(self):
        # Every writer must persist canonical block data: an upper-case
        # schedule_id from the LLM lands lower-cased, like the admin editor.
        from apps.cms.models import CMSEmbedWidget
        from apps.event.models import CurrentProjectSchedule

        CMSEmbedWidget.objects.create(widget_type="app_route", app_route="/schedule", slug="schedule-embed")
        schedule = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE,
            target_app_label="cms",
            target_model="CMSPage",
            title="Create schedule page",
            payload={
                "page": {
                    "slug": "ai-schedule",
                    "route": "/ai-schedule",
                    "title": "AI Schedule",
                    "status": "draft",
                    "blocks": [
                        {
                            "block_type": "embed_widget",
                            "data": {"slug": "schedule-embed", "schedule_id": str(schedule.pk).upper()},
                        }
                    ],
                }
            },
        )

        cms_actions.apply_cms_page_update(action)

        block = CMSPage.objects.get(slug="ai-schedule").blocks.get()
        self.assertEqual(block.data["schedule_id"], str(schedule.pk))

    def test_apply_cms_page_update_rejects_non_dict_payload(self):
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE,
            target_app_label="cms",
            target_model="CMSPage",
            title="Bad payload",
            payload={"page": "not a dict"},
        )
        with self.assertRaises(ActionRequestError) as cm:
            cms_actions.apply_cms_page_update(action)
        self.assertIn("Invalid CMS page action payload", str(cm.exception))

    def test_apply_cms_page_update_rejects_deleted_target(self):
        page = CMSPage.objects.create(slug="deleted", route="/deleted", title="Deleted", status="draft")
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE,
            target_app_label="cms",
            target_model="CMSPage",
            target_pk=str(page.pk),
            title="Stale CMS update",
            payload={
                "page": {
                    "slug": "deleted",
                    "route": "/deleted",
                    "title": "Should not be recreated",
                    "status": "draft",
                    "blocks": [],
                }
            },
        )
        page.delete()

        with self.assertRaises(ActionRequestError) as cm:
            cms_actions.apply_cms_page_update(action)

        self.assertIn("no longer exists", str(cm.exception))
        self.assertFalse(CMSPage.objects.filter(slug="deleted").exists())


# ---------------------------------------------------------------------------
# context/__init__.py
# ---------------------------------------------------------------------------
class ContextTests(SystemIntelligenceActionBase):
    def test_current_conversation_missing_row_raises(self):
        # Point the context var at a conversation id that does not exist.
        missing_tokens = actions.set_action_context("00000000-0000-0000-0000-000000000000", str(self.admin_user.pk))
        try:
            with self.assertRaises(ActionRequestError) as cm:
                current_conversation()
            self.assertIn("Active chat conversation was not found", str(cm.exception))
        finally:
            actions.reset_action_context(missing_tokens)

    def test_current_user_resolves_set_user(self):
        self.assertEqual(current_user(), self.admin_user)
        self.assertEqual(current_user_id(), str(self.admin_user.pk))

    def test_current_user_returns_none_when_user_missing(self):
        # A syntactically valid UUID that maps to no Member -> DoesNotExist -> None.
        bad_tokens = actions.set_action_context(str(self.conversation.pk), "22222222-2222-2222-2222-222222222222")
        try:
            self.assertIsNone(current_user())
        finally:
            actions.reset_action_context(bad_tokens)

    def test_current_user_returns_none_when_no_user_id_set(self):
        # No user id in context -> early return None without a DB lookup.
        no_user_tokens = actions.set_action_context(str(self.conversation.pk), None)
        try:
            self.assertIsNone(current_user())
        finally:
            actions.reset_action_context(no_user_tokens)
