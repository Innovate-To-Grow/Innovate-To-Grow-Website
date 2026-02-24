"""
Tests for HomePageAdmin workflow actions and bulk actions.

Covers:
- HomePageAdmin workflow button handling (submit_for_review, publish, unpublish, reject)
- HomePageAdmin bulk admin actions (publish, unpublish, submit_for_review)
- Status badge display for home pages
"""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from ...admin.content.home_page import HomePageAdmin
from ...models import HomePage

User = get_user_model()


class HomePageAdminWorkflowTest(TestCase):
    """Test HomePageAdmin workflow button handling."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(username="admin", password="admin123", email="admin@test.com")
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


class HomePageAdminBulkActionsTest(TestCase):
    """Test HomePageAdmin bulk actions."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(username="admin", password="admin123", email="admin@test.com")
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
