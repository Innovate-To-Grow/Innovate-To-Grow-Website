"""
Tests for PageAdmin bulk admin actions.

Covers:
- Bulk submit_for_review, publish, unpublish actions
"""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from ...admin.content.page import PageAdmin
from ...models import Page

User = get_user_model()


class MockMessages:
    """Mock Django messages framework for RequestFactory tests."""

    def __init__(self):
        self.messages = []

    def add(self, level, message, extra_tags=""):
        level_map = {
            20: "info",
            25: "success",
            30: "warning",
            40: "error",
        }
        self.messages.append((message, level_map.get(level, str(level))))

    def __iter__(self):
        return iter(self.messages)


class PageAdminBulkActionsTest(TestCase):
    """Test PageAdmin bulk actions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(username="admin", password="admin123", email="admin@test.com")
        self.site = AdminSite()
        self.page_admin = PageAdmin(Page, self.site)

    def _make_request(self):
        request = self.factory.post("/admin/pages/page/")
        request.user = self.admin_user
        request._messages = MockMessages()
        return request

    def test_bulk_submit_for_review(self):
        """Bulk action submits draft pages for review."""
        p1 = Page.objects.create(title="P1", slug="p1", status="draft")
        p2 = Page.objects.create(title="P2", slug="p2", status="draft")
        p3 = Page.objects.create(title="P3", slug="p3", status="published")

        queryset = Page.objects.filter(pk__in=[p1.pk, p2.pk, p3.pk])
        request = self._make_request()
        self.page_admin.action_submit_for_review(request, queryset)

        p1.refresh_from_db()
        p2.refresh_from_db()
        p3.refresh_from_db()
        self.assertEqual(p1.status, "review")
        self.assertEqual(p2.status, "review")
        self.assertEqual(p3.status, "published")  # Unchanged

    def test_bulk_publish(self):
        """Bulk action publishes draft and review pages."""
        p1 = Page.objects.create(title="P1", slug="p1", status="draft")
        p2 = Page.objects.create(title="P2", slug="p2", status="review")

        queryset = Page.objects.filter(pk__in=[p1.pk, p2.pk])
        request = self._make_request()
        self.page_admin.action_publish(request, queryset)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.status, "published")
        self.assertEqual(p2.status, "published")

    def test_bulk_unpublish(self):
        """Bulk action unpublishes published pages."""
        p1 = Page.objects.create(title="P1", slug="p1", status="published")
        p2 = Page.objects.create(title="P2", slug="p2", status="draft")

        queryset = Page.objects.filter(pk__in=[p1.pk, p2.pk])
        request = self._make_request()
        self.page_admin.action_unpublish(request, queryset)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.status, "draft")
        self.assertEqual(p2.status, "draft")  # Unchanged (was already draft)
