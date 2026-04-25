from django.urls import reverse

from cms.models import NewsFeedSource
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

    def _propose_update(self, source, name):
        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            payload = actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {"name": name})
        finally:
            actions.reset_action_context(tokens)
        return payload["action_request"]["id"]
