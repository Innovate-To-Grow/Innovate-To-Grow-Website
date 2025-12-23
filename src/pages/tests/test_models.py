from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from ..models import Page, Menu, MenuPageLink, HomePage, validate_nested_slug

class PageModelTest(TestCase):
    def test_create_page(self):
        page = Page.objects.create(title="Test Page", slug="test-page")
        self.assertEqual(page.title, "Test Page")
        self.assertEqual(page.slug, "test-page")
        self.assertEqual(page.slug_depth, 0)
        self.assertEqual(page.effective_meta_title, "Test Page")

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

    def test_get_url_external(self):
        ext_page = Page.objects.create(
            title="Ext", 
            slug="ext", 
            page_type="external", 
            external_url="https://google.com"
        )
        link = MenuPageLink.objects.create(menu=self.menu, page=ext_page)
        self.assertEqual(link.get_url(), "https://google.com")


class HomePageTest(TestCase):
    def test_active_toggle(self):
        h1 = HomePage.objects.create(name="H1", is_active=True)
        h2 = HomePage.objects.create(name="H2", is_active=False)
        
        self.assertTrue(HomePage.objects.get(pk=h1.pk).is_active)
        self.assertFalse(HomePage.objects.get(pk=h2.pk).is_active)

        # Set h2 active, h1 should become inactive
        h2.is_active = True
        h2.save()

        self.assertFalse(HomePage.objects.get(pk=h1.pk).is_active)
        self.assertTrue(HomePage.objects.get(pk=h2.pk).is_active)

    def test_get_active(self):
        HomePage.objects.create(name="H1", is_active=False)
        h2 = HomePage.objects.create(name="H2", is_active=True)
        self.assertEqual(HomePage.get_active(), h2)
