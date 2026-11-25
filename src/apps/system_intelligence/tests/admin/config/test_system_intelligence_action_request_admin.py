from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from apps.event.tests.helpers import make_admin
from apps.system_intelligence.admin.config.action_requests import SystemIntelligenceActionRequestAdmin
from apps.system_intelligence.models import ChatConversation, SystemIntelligenceActionRequest


class SystemIntelligenceActionRequestAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = make_admin()
        self.admin = SystemIntelligenceActionRequestAdmin(SystemIntelligenceActionRequest, AdminSite())

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.admin_user
        return request

    def test_no_add_permission(self):
        self.assertFalse(self.admin.has_add_permission(self._request()))

    def test_no_delete_permission(self):
        self.assertFalse(self.admin.has_delete_permission(self._request()))

    def test_every_admin_sees_every_action_request(self):
        other = make_admin(email="other@example.com")
        conversation = ChatConversation.objects.create(created_by=other, required_tool_apps=["cms", "event"])
        action = SystemIntelligenceActionRequest.objects.create(
            conversation=conversation,
            created_by=other,
            action_type=SystemIntelligenceActionRequest.ACTION_DB_UPDATE,
            target_app_label="cms",
            target_model="NewsFeedSource",
            target_pk="123",
            title="Update feed",
        )
        self.assertEqual(list(self.admin.get_queryset(self._request())), [action])
