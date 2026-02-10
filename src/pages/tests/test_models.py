from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from layout.models import Menu, MenuPageLink

from ..models import HomePage, Page, PageComponent, validate_nested_slug

User = get_user_model()


class PageModelTest(TestCase):
    def test_create_page(self):
        page = Page.objects.create(title="Test Page", slug="test-page")
        self.assertEqual(page.title, "Test Page")
        self.assertEqual(page.slug, "test-page")
        self.assertEqual(page.slug_depth, 0)
        self.assertEqual(page.effective_meta_title, "Test Page")
        self.assertEqual(list(page.ordered_components), [])

    def test_default_status_is_draft(self):
        page = Page.objects.create(title="Draft Page", slug="draft-page")
        self.assertEqual(page.status, "draft")
        self.assertFalse(page.published)

    def test_nested_slug_validation(self):
        # Valid slugs
        validate_nested_slug("valid-slug")
        validate_nested_slug("nested/slug")
        validate_nested_slug("deeply/nested/slug")

        # Invalid slugs
        with self.assertRaises(ValidationError):
            validate_nested_slug("/start-slash")
        with self.assertRaises(ValidationError):
            validate_nested_slug("end-slash/")
        with self.assertRaises(ValidationError):
            validate_nested_slug("double//slash")
        with self.assertRaises(ValidationError):
            validate_nested_slug("InvalidCase")
        with self.assertRaises(ValidationError):
            validate_nested_slug("space invalid")

    def test_slug_depth_update(self):
        page = Page.objects.create(title="Nested", slug="level1/level2/level3")
        self.assertEqual(page.slug_depth, 2)

    def test_meta_title_fallback(self):
        page = Page.objects.create(title="My Title", slug="my-title")
        self.assertEqual(page.meta_title, "My Title")

        page.meta_title = "SEO Title"
        page.save()
        self.assertEqual(page.effective_meta_title, "SEO Title")

    def test_get_absolute_url(self):
        page = Page.objects.create(title="Test", slug="test")
        self.assertEqual(page.get_absolute_url(), "/pages/test")

    def test_published_property(self):
        """Test that published property reflects status field."""
        page = Page.objects.create(title="Test", slug="pub-prop")
        self.assertFalse(page.published)

        page.status = "published"
        page.save()
        self.assertTrue(page.published)

        page.status = "review"
        page.save()
        self.assertFalse(page.published)

    def test_get_published_by_slug(self):
        """Test classmethod returns only published pages."""
        page = Page.objects.create(title="Test", slug="cached-page")
        # Draft page should not be found
        self.assertIsNone(Page.get_published_by_slug("cached-page"))

        # Publish it
        page.status = "published"
        page.save()
        result = Page.get_published_by_slug("cached-page")
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, page.pk)

    def test_get_published_by_slug_not_found(self):
        """Test classmethod returns None for nonexistent slug."""
        self.assertIsNone(Page.get_published_by_slug("nonexistent"))

    def test_str(self):
        page = Page.objects.create(title="About Us", slug="about-us")
        self.assertEqual(str(page), "about-us - About Us")


class PageComponentTest(TestCase):
    def test_requires_single_parent(self):
        page = Page.objects.create(title="P", slug="p")
        comp = PageComponent(name="Test", component_type="html", html_content="<p>Hi</p>")

        with self.assertRaises(ValidationError):
            comp.full_clean()

        comp.page = page
        comp.full_clean()  # no error once a parent is set

    def test_ordering(self):
        page = Page.objects.create(title="Ordered", slug="ordered")
        c2 = PageComponent.objects.create(name="C2", page=page, component_type="html", order=2, html_content="<p>2</p>")
        c1 = PageComponent.objects.create(name="C1", page=page, component_type="html", order=1, html_content="<p>1</p>")

        ordered = list(page.ordered_components)
        self.assertEqual(ordered, [c1, c2])


class MenuModelTest(TestCase):
    def setUp(self):
        self.page1 = Page.objects.create(title="Page 1", slug="page-1")
        self.page2 = Page.objects.create(title="Page 2", slug="page-2")
        self.menu = Menu.objects.create(name="main-nav", display_name="Main Navigation")

    def test_menu_creation(self):
        self.assertEqual(str(self.menu), "Main Navigation")

    def test_menu_page_links(self):
        link1 = MenuPageLink.objects.create(menu=self.menu, page=self.page1, order=2)
        link2 = MenuPageLink.objects.create(menu=self.menu, page=self.page2, order=1)

        links = self.menu.get_page_links()
        self.assertEqual(list(links), [link2, link1])

        pages = self.menu.get_pages()
        self.assertEqual(list(pages), [self.page2, self.page1])


class MenuPageLinkTest(TestCase):
    def setUp(self):
        self.page = Page.objects.create(title="Page 1", slug="page-1")
        self.menu = Menu.objects.create(name="main", display_name="Main")

    def test_display_title_override(self):
        link = MenuPageLink.objects.create(menu=self.menu, page=self.page)
        self.assertEqual(link.display_title, "Page 1")

        link.custom_title = "Custom"
        link.save()
        self.assertEqual(link.display_title, "Custom")

    def test_get_url_internal(self):
        link = MenuPageLink.objects.create(menu=self.menu, page=self.page)
        self.assertEqual(link.get_url(), "/pages/page-1")


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
