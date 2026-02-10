"""
Tests for admin workflow actions and UI behavior.

Covers:
- PageAdmin workflow button handling (submit_for_review, publish, unpublish, reject, rollback)
- HomePageAdmin workflow button handling
- Bulk admin actions (publish, unpublish, submit_for_review)
- Admin change_view context (versions, status)
- Status badge display
"""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from ..admin.home_page import HomePageAdmin
from ..admin.page import PageAdmin
from ..models import HomePage, Page

User = get_user_model()


class PageAdminWorkflowTest(TestCase):
    """Test PageAdmin workflow button handling via response_change."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(
            username="admin", password="admin123", email="admin@test.com"
        )
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


class PageAdminBulkActionsTest(TestCase):
    """Test PageAdmin bulk actions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(
            username="admin", password="admin123", email="admin@test.com"
        )
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


class HomePageAdminWorkflowTest(TestCase):
    """Test HomePageAdmin workflow button handling."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(
            username="admin", password="admin123", email="admin@test.com"
        )
        self.site = AdminSite()
        self.hp_admin = HomePageAdmin(HomePage, self.site)
        self.hp = HomePage.objects.create(name="Test Home")

    def _make_post_request(self, data):
        url = reverse("admin:pages_homepage_change", args=[self.hp.pk])
        request = self.factory.post(url, data=data)
        request.user = self.admin_user
        request._messages = MockMessages()
        return request

    def test_submit_for_review(self):
        request = self._make_post_request({"_submit_for_review": "1"})
        self.hp_admin.response_change(request, self.hp)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "review")

    def test_publish(self):
        self.hp.submit_for_review(user=self.admin_user)
        request = self._make_post_request({"_publish": "1"})
        self.hp_admin.response_change(request, self.hp)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "published")

    def test_unpublish(self):
        self.hp.publish(user=self.admin_user)
        self.hp.is_active = True
        self.hp.save()

        request = self._make_post_request({"_unpublish": "1"})
        self.hp_admin.response_change(request, self.hp)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "draft")
        self.assertFalse(self.hp.is_active)

    def test_reject_review(self):
        self.hp.submit_for_review(user=self.admin_user)
        request = self._make_post_request({"_reject_review": "1"})
        self.hp_admin.response_change(request, self.hp)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "draft")

    def test_status_badge(self):
        badge = self.hp_admin.status_badge(self.hp)
        self.assertIn("Draft", badge)

    def test_component_count(self):
        count = self.hp_admin.component_count(self.hp)
        self.assertEqual(count, 0)


class HomePageAdminBulkActionsTest(TestCase):
    """Test HomePageAdmin bulk actions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(
            username="admin", password="admin123", email="admin@test.com"
        )
        self.site = AdminSite()
        self.hp_admin = HomePageAdmin(HomePage, self.site)

    def _make_request(self):
        request = self.factory.post("/admin/pages/homepage/")
        request.user = self.admin_user
        request._messages = MockMessages()
        return request

    def test_bulk_submit_for_review(self):
        hp1 = HomePage.objects.create(name="HP1", status="draft")
        hp2 = HomePage.objects.create(name="HP2", status="published")

        queryset = HomePage.objects.filter(pk__in=[hp1.pk, hp2.pk])
        request = self._make_request()
        self.hp_admin.action_submit_for_review(request, queryset)

        hp1.refresh_from_db()
        hp2.refresh_from_db()
        self.assertEqual(hp1.status, "review")
        self.assertEqual(hp2.status, "published")  # Unchanged

    def test_bulk_publish(self):
        hp1 = HomePage.objects.create(name="HP1", status="draft")
        hp2 = HomePage.objects.create(name="HP2", status="review")

        queryset = HomePage.objects.filter(pk__in=[hp1.pk, hp2.pk])
        request = self._make_request()
        self.hp_admin.action_publish(request, queryset)

        hp1.refresh_from_db()
        hp2.refresh_from_db()
        self.assertEqual(hp1.status, "published")
        self.assertEqual(hp2.status, "published")

    def test_bulk_unpublish(self):
        hp1 = HomePage.objects.create(name="HP1", status="published")
        hp2 = HomePage.objects.create(name="HP2", status="draft")

        queryset = HomePage.objects.filter(pk__in=[hp1.pk, hp2.pk])
        request = self._make_request()
        self.hp_admin.action_unpublish(request, queryset)

        hp1.refresh_from_db()
        hp2.refresh_from_db()
        self.assertEqual(hp1.status, "draft")
        self.assertEqual(hp2.status, "draft")


class AdminChangeViewContextTest(TestCase):
    """Test that change_view passes correct context to template."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin", password="admin123", email="admin@test.com"
        )
        self.client.force_login(self.admin_user)

    def test_page_change_view_has_versions_context(self):
        """Page change view includes versions in context."""
        page = Page.objects.create(title="Ctx Page", slug="ctx-page")
        page.save_version(comment="Initial", user=self.admin_user)

        url = reverse("admin:pages_page_change", args=[page.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("versions", response.context)
        self.assertIn("current_status", response.context)
        self.assertEqual(response.context["current_status"], "draft")

    def test_homepage_change_view_has_versions_context(self):
        """HomePage change view includes versions in context."""
        hp = HomePage.objects.create(name="Ctx Home")
        hp.save_version(comment="Initial", user=self.admin_user)

        url = reverse("admin:pages_homepage_change", args=[hp.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("versions", response.context)
        self.assertIn("current_status", response.context)
        self.assertEqual(response.context["current_status"], "draft")


# ========================
# Mock helpers
# ========================


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
