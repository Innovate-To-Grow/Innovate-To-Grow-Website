"""
Tests for HomePage model publishing workflow transitions and version tracking.

Covers:
- HomePage workflow transitions (with is_active semantics)
- Version history creation on HomePage workflow actions
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from ...models import HomePage

User = get_user_model()


class HomePageWorkflowTransitionTest(TestCase):
    """Test publishing workflow transitions on HomePage model."""

    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")
        self.hp = HomePage.objects.create(name="Test Home")

    def test_initial_status_is_draft(self):
        self.assertEqual(self.hp.status, "draft")
        self.assertFalse(self.hp.published)
        self.assertFalse(self.hp.is_active)

    # ========================
    # submit_for_review
    # ========================

    def test_submit_for_review(self):
        self.hp.submit_for_review(user=self.user)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "review")
        self.assertIsNotNone(self.hp.submitted_for_review_at)
        self.assertEqual(self.hp.submitted_for_review_by, self.user)

    def test_submit_for_review_from_review_raises(self):
        self.hp.submit_for_review(user=self.user)
        with self.assertRaises(ValueError):
            self.hp.submit_for_review(user=self.user)

    # ========================
    # publish
    # ========================

    def test_publish_from_review(self):
        self.hp.submit_for_review(user=self.user)
        self.hp.publish(user=self.user)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "published")
        self.assertTrue(self.hp.published)
        self.assertIsNotNone(self.hp.published_at)

    def test_publish_directly_from_draft(self):
        self.hp.publish(user=self.user)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "published")
        self.assertTrue(self.hp.published)

    def test_publish_from_published_raises(self):
        self.hp.publish(user=self.user)
        with self.assertRaises(ValueError):
            self.hp.publish(user=self.user)

    # ========================
    # unpublish (with is_active semantics)
    # ========================

    def test_unpublish_deactivates(self):
        """Unpublishing a home page also sets is_active=False."""
        self.hp.publish(user=self.user)
        # Manually activate
        self.hp.is_active = True
        self.hp.save()
        self.assertTrue(self.hp.is_active)

        self.hp.unpublish(user=self.user)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "draft")
        self.assertFalse(self.hp.is_active)

    # ========================
    # reject_review
    # ========================

    def test_reject_review(self):
        self.hp.submit_for_review(user=self.user)
        self.hp.reject_review(user=self.user)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "draft")

    def test_reject_review_from_draft_raises(self):
        with self.assertRaises(ValueError):
            self.hp.reject_review(user=self.user)

    # ========================
    # is_active validation
    # ========================

    def test_cannot_activate_draft(self):
        """Cannot set is_active=True on a draft home page."""
        with self.assertRaises(ValidationError):
            HomePage.objects.create(name="Bad", status="draft", is_active=True)

    def test_cannot_activate_review(self):
        """Cannot set is_active=True on a home page in review."""
        with self.assertRaises(ValidationError):
            HomePage.objects.create(name="Bad", status="review", is_active=True)

    def test_can_activate_published(self):
        """Can set is_active=True on a published home page."""
        hp = HomePage.objects.create(name="Good", status="published", is_active=True)
        self.assertTrue(hp.is_active)

    def test_activate_deactivates_others(self):
        """Setting one home page active deactivates all others."""
        hp1 = HomePage.objects.create(name="HP1", status="published", is_active=True)
        hp2 = HomePage.objects.create(name="HP2", status="published", is_active=False)

        hp2.is_active = True
        hp2.save()

        hp1.refresh_from_db()
        hp2.refresh_from_db()
        self.assertFalse(hp1.is_active)
        self.assertTrue(hp2.is_active)


class HomePageWorkflowVersionTest(TestCase):
    """Test that HomePage workflow transitions create version records."""

    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")
        self.hp = HomePage.objects.create(name="Version Home")

    def test_submit_for_review_creates_version(self):
        initial_count = len(self.hp.get_versions())
        self.hp.submit_for_review(user=self.user)
        self.assertGreater(len(self.hp.get_versions()), initial_count)

    def test_publish_creates_version(self):
        self.hp.submit_for_review(user=self.user)
        initial_count = len(self.hp.get_versions())
        self.hp.publish(user=self.user)
        self.assertGreater(len(self.hp.get_versions()), initial_count)

    def test_unpublish_creates_version(self):
        self.hp.publish(user=self.user)
        initial_count = len(self.hp.get_versions())
        self.hp.unpublish(user=self.user)
        self.assertGreater(len(self.hp.get_versions()), initial_count)

    def test_reject_creates_version(self):
        self.hp.submit_for_review(user=self.user)
        initial_count = len(self.hp.get_versions())
        self.hp.reject_review(user=self.user)
        self.assertGreater(len(self.hp.get_versions()), initial_count)
