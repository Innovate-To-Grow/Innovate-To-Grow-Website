"""
Tests for admin change_view context (versions, status).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ...models import HomePage, Page

User = get_user_model()


class AdminChangeViewContextTest(TestCase):
    """Test that change_view passes correct context to template."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(username="admin", password="admin123", email="admin@test.com")
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

    def test_page_change_view_renders(self):
        """Page change view loads without errors."""
        page = Page.objects.create(title="Render Test", slug="render-test")
        url = reverse("admin:pages_page_change", args=[page.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_homepage_change_view_renders(self):
        """HomePage change view loads without errors."""
        hp = HomePage.objects.create(name="Render Home")
        url = reverse("admin:pages_homepage_change", args=[hp.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
