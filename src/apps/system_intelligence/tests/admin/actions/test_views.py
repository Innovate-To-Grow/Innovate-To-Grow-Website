import uuid
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.cms.models import CMSBlock, CMSPage, NewsFeedSource
from apps.event.tests.helpers import make_superuser
from apps.system_intelligence.models import ChatConversation, SystemIntelligenceActionRequest
from apps.system_intelligence.services import actions
from apps.system_intelligence.tests.admin.base import SystemIntelligenceAdminBase


class ActionApproveRejectViewTests(SystemIntelligenceAdminBase):
    def _propose_update(self, source, name):
        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            payload = actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {"name": name})
        finally:
            actions.reset_action_context(tokens)
        return payload["action_request"]["id"]

    def _make_source(self):
        return NewsFeedSource.objects.create(name="Feed", source_key="feed", feed_url="https://example.com/feed.xml")

    def test_approve_requires_post(self):
        source = self._make_source()
        action_id = self._propose_update(source, "Renamed")
        response = self.client.get(reverse("admin:system_intelligence_action_approve", args=[action_id]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"], "POST required")

    def test_reject_requires_post(self):
        source = self._make_source()
        action_id = self._propose_update(source, "Renamed")
        response = self.client.get(reverse("admin:system_intelligence_action_reject", args=[action_id]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"], "POST required")

    def test_approve_unknown_action_returns_404_permission_message(self):
        response = self.client.post(reverse("admin:system_intelligence_action_approve", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Action request not found.")

    def test_reject_unknown_action_returns_404_permission_message(self):
        response = self.client.post(reverse("admin:system_intelligence_action_reject", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Action request not found.")

    def test_approve_action_owned_by_other_user_returns_404(self):
        other = make_superuser(email="other@example.com")
        other_convo = ChatConversation.objects.create(created_by=other)
        source = self._make_source()
        tokens = actions.set_action_context(str(other_convo.pk), str(other.pk))
        try:
            payload = actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {"name": "X"})
        finally:
            actions.reset_action_context(tokens)
        action_id = payload["action_request"]["id"]
        response = self.client.post(reverse("admin:system_intelligence_action_approve", args=[action_id]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Action request not found.")

    def test_approve_already_applied_returns_action_request_error(self):
        source = self._make_source()
        action_id = self._propose_update(source, "First")
        self.client.post(reverse("admin:system_intelligence_action_approve", args=[action_id]))
        # Second approve: action is now applied, raising ActionRequestError.
        response = self.client.post(reverse("admin:system_intelligence_action_approve", args=[action_id]))
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["error"], "Could not process this action request.")
        self.assertEqual(body["action_request"]["status"], "applied")

    def test_reject_already_rejected_returns_action_request_error(self):
        source = self._make_source()
        action_id = self._propose_update(source, "First")
        self.client.post(reverse("admin:system_intelligence_action_reject", args=[action_id]))
        response = self.client.post(reverse("admin:system_intelligence_action_reject", args=[action_id]))
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["error"], "Could not process this action request.")
        self.assertEqual(body["action_request"]["status"], "rejected")

    def test_approve_permission_denied_during_apply_returns_generic_permission_error(self):
        source = self._make_source()
        action_id = self._propose_update(source, "Denied")
        with patch.object(actions, "approve_action_request", side_effect=PermissionDenied("no perm")):
            response = self.client.post(reverse("admin:system_intelligence_action_approve", args=[action_id]))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Action request not found.")

    def test_approve_validation_error_returns_generic_validation_error(self):
        source = self._make_source()
        action_id = self._propose_update(source, "Invalid")
        with patch.object(actions, "approve_action_request", side_effect=ValidationError("bad field")):
            response = self.client.post(reverse("admin:system_intelligence_action_approve", args=[action_id]))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Validation failed for the proposed change.")

    def test_approve_unexpected_error_returns_generic_action_error(self):
        source = self._make_source()
        action_id = self._propose_update(source, "Boom")
        with patch.object(actions, "approve_action_request", side_effect=ValueError("unexpected")):
            response = self.client.post(reverse("admin:system_intelligence_action_approve", args=[action_id]))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Could not process this action request.")


class ActionPreviewViewErrorTests(SystemIntelligenceAdminBase):
    def test_preview_unknown_action_returns_404(self):
        response = self.client.get(reverse("admin:system_intelligence_action_preview", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)

    def test_full_preview_unknown_action_returns_404(self):
        response = self.client.get(reverse("admin:system_intelligence_action_full_preview", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)

    def test_preview_non_cms_action_returns_404(self):
        source = NewsFeedSource.objects.create(name="Feed", source_key="feed", feed_url="https://example.com/feed.xml")
        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            payload = actions.propose_db_update("cms", "NewsFeedSource", str(source.pk), {"name": "Renamed"})
        finally:
            actions.reset_action_context(tokens)
        action_id = payload["action_request"]["id"]
        response = self.client.get(reverse("admin:system_intelligence_action_preview", args=[action_id]))
        self.assertEqual(response.status_code, 404)

    def test_full_preview_returns_404_when_no_page_payload(self):
        # A CMS action whose payload has no usable page dict yields page None.
        page = CMSPage.objects.create(slug="np", route="/np", title="NP", status="draft")
        CMSBlock.objects.create(page=page, block_type="rich_text", sort_order=0, data={"body_html": "<p>x</p>"})
        tokens = actions.set_action_context(str(self.conversation.pk), str(self.admin_user.pk))
        try:
            payload = actions.propose_cms_page_update(
                page_id=str(page.pk),
                blocks=[{"block_type": "rich_text", "data": {"heading": "H", "body_html": "<p>y</p>"}}],
            )
        finally:
            actions.reset_action_context(tokens)
        action = SystemIntelligenceActionRequest.objects.get(id=payload["action_request"]["id"])
        # Wipe the cache preview and the stored page payload so _cms_preview_page returns None.
        from django.core.cache import cache

        cache.delete(f"cms:preview:{action.preview_token}")
        action.payload = {"page": "not-a-dict"}
        action.save(update_fields=["payload", "updated_at"])
        response = self.client.get(reverse("admin:system_intelligence_action_full_preview", args=[action.id]))
        self.assertEqual(response.status_code, 404)
