from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from apps.event.tests.helpers import make_superuser
from apps.system_intelligence.admin.config.action_requests import SystemIntelligenceActionRequestAdmin
from apps.system_intelligence.models import (
    SystemIntelligenceActionRequest,
)


class SystemIntelligenceActionRequestAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = make_superuser()
        self.admin = SystemIntelligenceActionRequestAdmin(SystemIntelligenceActionRequest, AdminSite())

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.admin_user
        return request

    def test_no_add_permission(self):
        self.assertFalse(self.admin.has_add_permission(self._request()))

    def test_no_delete_permission(self):
        self.assertFalse(self.admin.has_delete_permission(self._request()))
