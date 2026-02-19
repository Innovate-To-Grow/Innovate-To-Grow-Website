"""
Tests for Page workflow version tracking.

Covers:
- Version history creation on Page workflow actions
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from ...models import Page

User = get_user_model()


class PageWorkflowVersionTest(TestCase):
    """Test that workflow transitions create version records."""

    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")
        self.page = Page.objects.create(title="Version Page", slug="version-page")

    def test_submit_for_review_creates_version(self):
        initial_count = len(self.page.get_versions())
        self.page.submit_for_review(user=self.user)
        versions = self.page.get_versions()
        self.assertGreater(len(versions), initial_count)
        latest = versions[0]  # Most recent version
        self.assertIn("review", latest.comment.lower())

    def test_publish_creates_version(self):
        self.page.submit_for_review(user=self.user)
        initial_count = len(self.page.get_versions())
        self.page.publish(user=self.user)
        versions = self.page.get_versions()
        self.assertGreater(len(versions), initial_count)

    def test_unpublish_creates_version(self):
        self.page.publish(user=self.user)
        initial_count = len(self.page.get_versions())
        self.page.unpublish(user=self.user)
        versions = self.page.get_versions()
        self.assertGreater(len(versions), initial_count)

    def test_reject_review_creates_version(self):
        self.page.submit_for_review(user=self.user)
        initial_count = len(self.page.get_versions())
        self.page.reject_review(user=self.user)
        versions = self.page.get_versions()
        self.assertGreater(len(versions), initial_count)
