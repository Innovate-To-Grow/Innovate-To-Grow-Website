"""
Tests for PageAdmin workflow actions and bulk actions.

Covers:
- PageAdmin workflow button handling (submit_for_review, publish, unpublish, reject, rollback)
- PageAdmin bulk admin actions (publish, unpublish, submit_for_review)
- Status badge display for pages
"""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from ...admin.content.page import PageAdmin
from ...models import Page

User = get_user_model()


class PageAdminWorkflowTest(TestCase):
    """Test PageAdmin workflow button handling via response_change."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(username="admin", password="admin123", email="admin@test.com")
        self.site = AdminSite()
        self.page_admin = PageAdmin(Page, self.site)
        self.page = Page.objects.create(title="Test Page", slug="admin-test")

    def _make_post_request(self, data):
        """Helper to create a POST request with admin user."""
        url = reverse("admin:pages_page_change", args=[self.page.pk])
        request = self.factory.post(url, data=data)
        request.user = self.admin_user
        return request

    def test_submit_for_review(self):
        """Clicking Submit for Review transitions to review status."""
        request = self._make_post_request({"_submit_for_review": "1"})
        # Simulate Django admin message framework
        request._messages = MockMessages()
        self.page_admin.response_change(request, self.page)

        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "review")

    def test_publish(self):
        """Clicking Publish transitions to published status."""
        self.page.submit_for_review(user=self.admin_user)

        request = self._make_post_request({"_publish": "1"})
        request._messages = MockMessages()
        self.page_admin.response_change(request, self.page)

        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "published")

    def test_unpublish(self):
        """Clicking Unpublish transitions to draft status."""
        self.page.publish(user=self.admin_user)

        request = self._make_post_request({"_unpublish": "1"})
        request._messages = MockMessages()
        self.page_admin.response_change(request, self.page)

        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")

    def test_reject_review(self):
        """Clicking Reject transitions review -> draft."""
        self.page.submit_for_review(user=self.admin_user)

        request = self._make_post_request({"_reject_review": "1"})
        request._messages = MockMessages()
        self.page_admin.response_change(request, self.page)

        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")

    def test_reject_from_draft_shows_error(self):
        """Rejecting from draft status shows error message."""
        request = self._make_post_request({"_reject_review": "1"})
        messages = MockMessages()
        request._messages = messages
        self.page_admin.response_change(request, self.page)

        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")  # unchanged
        # Should have an error message
        self.assertTrue(any(m[1] == "error" for m in messages.messages))

    def test_rollback_button(self):
        """Clicking Rollback calls obj.rollback and returns redirect."""
        # Create a version to rollback to
        self.page.save_version(comment="Version 1", user=self.admin_user)

        versions = self.page.get_versions()
        self.assertGreater(len(versions), 0)
        target_version = versions[0].version_number

        request = self._make_post_request({"_rollback": str(target_version)})
        messages = MockMessages()
        request._messages = messages
        response = self.page_admin.response_change(request, self.page)

        # Should return a redirect (302)
        self.assertEqual(response.status_code, 302)

    def test_rollback_invalid_version(self):
        """Rollback with invalid version number shows error."""
        request = self._make_post_request({"_rollback": "999"})
        messages = MockMessages()
        request._messages = messages
        self.page_admin.response_change(request, self.page)
        # Should have an error message
        self.assertTrue(any(m[1] == "error" for m in messages.messages))

    def test_status_badge(self):
        """status_badge returns colored HTML."""
        badge = self.page_admin.status_badge(self.page)
        self.assertIn("Draft", badge)

        self.page.publish(user=self.admin_user)
        badge = self.page_admin.status_badge(self.page)
        self.assertIn("Published", badge)


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
