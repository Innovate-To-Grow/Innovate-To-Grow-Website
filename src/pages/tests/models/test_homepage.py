from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from ...models import HomePage

User = get_user_model()


class HomePageTest(TestCase):
    def test_active_toggle(self):
        """Test that setting one home page active deactivates others."""
        # Must be published to be active
        h1 = HomePage.objects.create(name="H1", status="published", is_active=True)
        h2 = HomePage.objects.create(name="H2", status="published", is_active=False)

        self.assertTrue(HomePage.objects.get(pk=h1.pk).is_active)
        self.assertFalse(HomePage.objects.get(pk=h2.pk).is_active)

        # Set h2 active, h1 should become inactive
        h2.is_active = True
        h2.save()

        self.assertFalse(HomePage.objects.get(pk=h1.pk).is_active)
        self.assertTrue(HomePage.objects.get(pk=h2.pk).is_active)

    def test_get_active(self):
        """Test get_active returns the active published home page."""
        HomePage.objects.create(name="H1", is_active=False)
        h2 = HomePage.objects.create(name="H2", status="published", is_active=True)
        self.assertEqual(HomePage.get_active(), h2)

    def test_get_active_none(self):
        """Test get_active returns None when no active published home page exists."""
        HomePage.objects.create(name="H1", is_active=False)
        self.assertIsNone(HomePage.get_active())

    def test_cannot_activate_draft(self):
        """Test that a draft home page cannot be set as active."""
        with self.assertRaises(ValidationError):
            HomePage.objects.create(name="Draft", status="draft", is_active=True)

    def test_cannot_activate_review(self):
        """Test that a home page in review cannot be set as active."""
        with self.assertRaises(ValidationError):
            HomePage.objects.create(name="Review", status="review", is_active=True)

    def test_default_status_is_draft(self):
        hp = HomePage.objects.create(name="New")
        self.assertEqual(hp.status, "draft")
        self.assertFalse(hp.published)
        self.assertFalse(hp.is_active)

    def test_published_property(self):
        """Test backward-compatible published property."""
        hp = HomePage.objects.create(name="Test")
        self.assertFalse(hp.published)

        hp.status = "published"
        hp.save()
        self.assertTrue(hp.published)

    def test_str_representation(self):
        hp = HomePage.objects.create(name="My Home", status="published", is_active=True)
        self.assertIn("My Home", str(hp))
        self.assertIn("Active", str(hp))
        self.assertIn("Published", str(hp))


class HomePageAuthoredModelTest(TestCase):
    """Test that HomePage has created_by/updated_by from AuthoredModel."""

    def setUp(self):
        self.user = User.objects.create_user(username="author", password="testpass123")

    def test_homepage_has_created_by_field(self):
        hp = HomePage(name="Authored", created_by=self.user)
        hp.save()
        hp.refresh_from_db()
        self.assertEqual(hp.created_by, self.user)

    def test_homepage_has_updated_by_field(self):
        hp = HomePage(name="Authored", updated_by=self.user)
        hp.save()
        hp.refresh_from_db()
        self.assertEqual(hp.updated_by, self.user)

    def test_homepage_created_by_nullable(self):
        hp = HomePage.objects.create(name="No Author")
        self.assertIsNone(hp.created_by)
        self.assertIsNone(hp.updated_by)


class HomePageUnpublishOverrideTest(TestCase):
    """Test that HomePage.unpublish() atomically deactivates + reverts to draft."""

    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")

    def test_unpublish_deactivates_and_reverts(self):
        hp = HomePage.objects.create(name="Active HP", status="published", is_active=True)
        hp.unpublish(user=self.user)
        hp.refresh_from_db()
        self.assertEqual(hp.status, "draft")
        self.assertFalse(hp.is_active)

    def test_unpublish_creates_version(self):
        hp = HomePage.objects.create(name="Version HP", status="published", is_active=True)
        initial_count = len(hp.get_versions())
        hp.unpublish(user=self.user)
        self.assertGreater(len(hp.get_versions()), initial_count)

    def test_unpublish_already_draft_still_deactivates(self):
        hp = HomePage.objects.create(name="Draft HP")
        hp.unpublish(user=self.user)
        hp.refresh_from_db()
        self.assertEqual(hp.status, "draft")
        self.assertFalse(hp.is_active)
