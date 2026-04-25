from core.models.base.system_intelligence import SystemIntelligenceActionRequest
from core.services import system_intelligence_actions as actions

from .base import SystemIntelligenceActionBase


class SystemIntelligenceComparisonTests(SystemIntelligenceActionBase):
    def test_cms_comparison_falls_back_from_snapshots_and_truncates_large_text(self):
        long_text = "A" * 1200
        before = {
            "title": "Page",
            "route": "/page",
            "blocks": [
                {
                    "block_type": "rich_text",
                    "sort_order": 0,
                    "admin_label": "Main copy",
                    "data": {"body_html": "<p>Short</p>"},
                }
            ],
        }
        after = {
            "title": "Page",
            "route": "/page",
            "blocks": [
                {
                    "block_type": "rich_text",
                    "sort_order": 0,
                    "admin_label": "Main copy",
                    "data": {"body_html": f"<p>{long_text}</p>"},
                }
            ],
        }
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=self.conversation,
            created_by=self.admin_user,
            action_type=SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE,
            target_app_label="cms",
            target_model="CMSPage",
            title="Legacy CMS action",
            payload={"page": after},
            before_snapshot=before,
            after_snapshot=after,
            diff=[],
        )
        block = actions.serialize_action_request(action)["comparison"]["blocks"][0]
        self.assertEqual(block["before_text"], "Short")
        self.assertLessEqual(len(block["after_text"]), actions.COMPARISON_TEXT_LIMIT)
        self.assertTrue(block["after_text"].endswith("..."))
