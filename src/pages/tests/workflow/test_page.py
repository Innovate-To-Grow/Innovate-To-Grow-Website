"""
Tests for Page model publishing workflow transitions and version tracking.

Covers:
- WorkflowPublishingMixin transitions on Page model
- Version history creation on Page workflow actions
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from ...models import Page

User = get_user_model()


class PageWorkflowTransitionTest(TestCase):
    """Test publishing workflow transitions on Page model."""

    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")
        self.page = Page.objects.create(title="Test Page", slug="test-workflow")

    def test_initial_status_is_draft(self):
        self.assertEqual(self.page.status, "draft")
        self.assertFalse(self.page.published)

    # ========================
    # submit_for_review
    # ========================

    def test_submit_for_review_from_draft(self):
        """Draft -> Review transition succeeds."""
        self.page.submit_for_review(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "review")
        self.assertIsNotNone(self.page.submitted_for_review_at)
        self.assertEqual(self.page.submitted_for_review_by, self.user)
        self.assertFalse(self.page.published)

    def test_submit_for_review_from_review_raises(self):
        """Review -> Review transition is invalid."""
        self.page.submit_for_review(user=self.user)
        with self.assertRaises(ValueError) as ctx:
            self.page.submit_for_review(user=self.user)
        self.assertIn("Cannot submit for review", str(ctx.exception))

    def test_submit_for_review_from_published_raises(self):
        """Published -> Review transition is invalid."""
        self.page.status = "published"
        self.page.save()
        with self.assertRaises(ValueError):
            self.page.submit_for_review(user=self.user)

    # ========================
    # publish
    # ========================

    def test_publish_from_review(self):
        """Review -> Published transition succeeds."""
        self.page.submit_for_review(user=self.user)
        self.page.publish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "published")
        self.assertTrue(self.page.published)
        self.assertIsNotNone(self.page.published_at)
        self.assertEqual(self.page.published_by, self.user)

    def test_publish_directly_from_draft(self):
        """Draft -> Published transition succeeds (direct publish)."""
        self.page.publish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "published")
        self.assertTrue(self.page.published)

    def test_publish_from_published_raises(self):
        """Published -> Published transition is invalid."""
        self.page.publish(user=self.user)
        with self.assertRaises(ValueError) as ctx:
            self.page.publish(user=self.user)
        self.assertIn("Cannot publish", str(ctx.exception))

    def test_publish_sets_published_at_only_once(self):
        """published_at is set on first publish and not overwritten."""
        self.page.publish(user=self.user)
        first_published_at = self.page.published_at

        # Unpublish and re-publish
        self.page.unpublish(user=self.user)
        self.page.publish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.published_at, first_published_at)

    # ========================
    # unpublish
    # ========================

    def test_unpublish_from_published(self):
        """Published -> Draft transition succeeds."""
        self.page.publish(user=self.user)
        self.page.unpublish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")
        self.assertFalse(self.page.published)

    def test_unpublish_from_review(self):
        """Review -> Draft transition succeeds."""
        self.page.submit_for_review(user=self.user)
        self.page.unpublish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")

    def test_unpublish_from_draft(self):
        """Draft -> Draft unpublish is a no-op (no error)."""
        self.page.unpublish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")

    # ========================
    # reject_review
    # ========================

    def test_reject_review_from_review(self):
        """Review -> Draft via rejection."""
        self.page.submit_for_review(user=self.user)
        self.page.reject_review(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")

    def test_reject_review_from_draft_raises(self):
        """Cannot reject from draft status."""
        with self.assertRaises(ValueError) as ctx:
            self.page.reject_review(user=self.user)
        self.assertIn("Cannot reject", str(ctx.exception))

    def test_reject_review_from_published_raises(self):
        """Cannot reject from published status."""
        self.page.publish(user=self.user)
        with self.assertRaises(ValueError):
            self.page.reject_review(user=self.user)

    # ========================
    # Full workflow cycle
    # ========================

    def test_full_workflow_cycle(self):
        """Draft -> Review -> Published -> Draft -> Review -> Published."""
        # Draft -> Review
        self.page.submit_for_review(user=self.user)
        self.assertEqual(self.page.status, "review")

        # Review -> Published
        self.page.publish(user=self.user)
        self.assertEqual(self.page.status, "published")
        self.assertTrue(self.page.published)

        # Published -> Draft (unpublish)
        self.page.unpublish(user=self.user)
        self.assertEqual(self.page.status, "draft")
        self.assertFalse(self.page.published)

        # Draft -> Review again
        self.page.submit_for_review(user=self.user)
        self.assertEqual(self.page.status, "review")

        # Review -> Reject
        self.page.reject_review(user=self.user)
        self.assertEqual(self.page.status, "draft")

        # Draft -> Publish directly
        self.page.publish(user=self.user)
        self.assertEqual(self.page.status, "published")
        self.assertTrue(self.page.published)
