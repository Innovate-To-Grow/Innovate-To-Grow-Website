"""
Tests for workflow transitions without a user.

Covers:
- Workflow transitions with user=None
"""

from django.test import TestCase

from ...models import HomePage, Page


class WorkflowWithoutUserTest(TestCase):
    """Test workflow transitions work without a user (user=None)."""

    def test_page_workflow_without_user(self):
        page = Page.objects.create(title="No User", slug="no-user")

        page.submit_for_review()
        page.refresh_from_db()
        self.assertEqual(self.page_status(page), "review")
        self.assertIsNone(page.submitted_for_review_by)

        page.publish()
        page.refresh_from_db()
        self.assertEqual(self.page_status(page), "published")
        self.assertIsNone(page.published_by)

        page.unpublish()
        page.refresh_from_db()
        self.assertEqual(self.page_status(page), "draft")

    def test_homepage_workflow_without_user(self):
        hp = HomePage.objects.create(name="No User Home")

        hp.submit_for_review()
        hp.refresh_from_db()
        self.assertEqual(hp.status, "review")
        self.assertIsNone(hp.submitted_for_review_by)

        hp.publish()
        hp.refresh_from_db()
        self.assertEqual(hp.status, "published")
        self.assertIsNone(hp.published_by)

    @staticmethod
    def page_status(page):
        return page.status
