from django.core.exceptions import ValidationError
from django.test import TestCase

from ...models import Menu, MenuPageLink, Page, PageComponent, PageComponentPlacement, validate_nested_slug


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
    def test_allows_any_parent_combination(self):
        """Test that a PageComponent can be created, and placements can link it to page/homepage."""
        page = Page.objects.create(title="P", slug="p")
        comp = PageComponent(name="Test", component_type="html", html_content="<p>Hi</p>")

        # No parent is allowed (component exists without placement)
        comp.full_clean()

        # Component can be linked to a page via placement
        comp.save()
        PageComponentPlacement.objects.create(component=comp, page=page, order=1)

    def test_ordering(self):
        page = Page.objects.create(title="Ordered", slug="ordered")
        c1 = PageComponent.objects.create(name="C1", component_type="html", html_content="<p>1</p>")
        c2 = PageComponent.objects.create(name="C2", component_type="html", html_content="<p>2</p>")
        PageComponentPlacement.objects.create(component=c2, page=page, order=2)
        PageComponentPlacement.objects.create(component=c1, page=page, order=1)

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
