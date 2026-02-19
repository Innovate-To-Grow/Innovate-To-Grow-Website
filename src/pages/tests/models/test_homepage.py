from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from ...models import HomePage, Page, PageComponent

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


class ComponentPageMixinTest(TestCase):
    """Test that ComponentPageMixin provides ordered_components/all_components on both models."""

    def test_page_ordered_components_filters_disabled(self):
        """ordered_components only returns enabled components."""
        page = Page.objects.create(title="Test", slug="mixin-ordered")
        c1 = PageComponent.objects.create(
            page=page,
            name="Enabled",
            component_type="html",
            order=1,
            is_enabled=True,
            html_content="<p>yes</p>",
        )
        PageComponent.objects.create(
            page=page,
            name="Disabled",
            component_type="html",
            order=2,
            is_enabled=False,
            html_content="<p>no</p>",
        )
        result = list(page.ordered_components)
        self.assertEqual(result, [c1])

    def test_page_all_components_includes_disabled(self):
        """all_components returns all components including disabled."""
        page = Page.objects.create(title="Test", slug="mixin-all")
        PageComponent.objects.create(
            page=page,
            name="Enabled",
            component_type="html",
            order=1,
            is_enabled=True,
            html_content="<p>yes</p>",
        )
        PageComponent.objects.create(
            page=page,
            name="Disabled",
            component_type="html",
            order=2,
            is_enabled=False,
            html_content="<p>no</p>",
        )
        self.assertEqual(page.all_components.count(), 2)

    def test_page_ordered_components_respects_order(self):
        """ordered_components sorts by order then id."""
        page = Page.objects.create(title="Test", slug="mixin-order")
        c3 = PageComponent.objects.create(
            page=page,
            name="Third",
            component_type="html",
            order=3,
            html_content="<p>3</p>",
        )
        c1 = PageComponent.objects.create(
            page=page,
            name="First",
            component_type="html",
            order=1,
            html_content="<p>1</p>",
        )
        c2 = PageComponent.objects.create(
            page=page,
            name="Second",
            component_type="html",
            order=2,
            html_content="<p>2</p>",
        )
        self.assertEqual(list(page.ordered_components), [c1, c2, c3])

    def test_homepage_ordered_components(self):
        """HomePage also has ordered_components via ComponentPageMixin."""
        hp = HomePage.objects.create(name="HP Mixin Test")
        c_enabled = PageComponent.objects.create(
            home_page=hp,
            name="Enabled",
            component_type="html",
            order=1,
            is_enabled=True,
            html_content="<h1>Hi</h1>",
        )
        PageComponent.objects.create(
            home_page=hp,
            name="Disabled",
            component_type="html",
            order=0,
            is_enabled=False,
            html_content="<h1>No</h1>",
        )
        result = list(hp.ordered_components)
        self.assertEqual(result, [c_enabled])

    def test_homepage_all_components(self):
        """HomePage also has all_components via ComponentPageMixin."""
        hp = HomePage.objects.create(name="HP All Test")
        PageComponent.objects.create(
            home_page=hp,
            name="C1",
            component_type="html",
            order=1,
            is_enabled=True,
            html_content="<p>1</p>",
        )
        PageComponent.objects.create(
            home_page=hp,
            name="C2",
            component_type="html",
            order=2,
            is_enabled=False,
            html_content="<p>2</p>",
        )
        self.assertEqual(hp.all_components.count(), 2)


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
