from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from ..models import GoogleSheet, HomePage, Menu, MenuPageLink, Page, PageComponent, UniformForm, validate_nested_slug

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


class ComponentPageMixinTest(TestCase):
    """Test that ComponentPageMixin provides ordered_components/all_components on both models."""

    def test_page_ordered_components_filters_disabled(self):
        """ordered_components only returns enabled components."""
        page = Page.objects.create(title="Test", slug="mixin-ordered")
        c1 = PageComponent.objects.create(
            page=page, name="Enabled", component_type="html", order=1,
            is_enabled=True, html_content="<p>yes</p>",
        )
        PageComponent.objects.create(
            page=page, name="Disabled", component_type="html", order=2,
            is_enabled=False, html_content="<p>no</p>",
        )
        result = list(page.ordered_components)
        self.assertEqual(result, [c1])

    def test_page_all_components_includes_disabled(self):
        """all_components returns all components including disabled."""
        page = Page.objects.create(title="Test", slug="mixin-all")
        PageComponent.objects.create(
            page=page, name="Enabled", component_type="html", order=1,
            is_enabled=True, html_content="<p>yes</p>",
        )
        PageComponent.objects.create(
            page=page, name="Disabled", component_type="html", order=2,
            is_enabled=False, html_content="<p>no</p>",
        )
        self.assertEqual(page.all_components.count(), 2)

    def test_page_ordered_components_respects_order(self):
        """ordered_components sorts by order then id."""
        page = Page.objects.create(title="Test", slug="mixin-order")
        c3 = PageComponent.objects.create(
            page=page, name="Third", component_type="html", order=3,
            html_content="<p>3</p>",
        )
        c1 = PageComponent.objects.create(
            page=page, name="First", component_type="html", order=1,
            html_content="<p>1</p>",
        )
        c2 = PageComponent.objects.create(
            page=page, name="Second", component_type="html", order=2,
            html_content="<p>2</p>",
        )
        self.assertEqual(list(page.ordered_components), [c1, c2, c3])

    def test_homepage_ordered_components(self):
        """HomePage also has ordered_components via ComponentPageMixin."""
        hp = HomePage.objects.create(name="HP Mixin Test")
        c_enabled = PageComponent.objects.create(
            home_page=hp, name="Enabled", component_type="html", order=1,
            is_enabled=True, html_content="<h1>Hi</h1>",
        )
        PageComponent.objects.create(
            home_page=hp, name="Disabled", component_type="html", order=0,
            is_enabled=False, html_content="<h1>No</h1>",
        )
        result = list(hp.ordered_components)
        self.assertEqual(result, [c_enabled])

    def test_homepage_all_components(self):
        """HomePage also has all_components via ComponentPageMixin."""
        hp = HomePage.objects.create(name="HP All Test")
        PageComponent.objects.create(
            home_page=hp, name="C1", component_type="html", order=1,
            is_enabled=True, html_content="<p>1</p>",
        )
        PageComponent.objects.create(
            home_page=hp, name="C2", component_type="html", order=2,
            is_enabled=False, html_content="<p>2</p>",
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


class ComponentTypeRestrictionTest(TestCase):
    """Test that component_type only allows supported values."""

    def test_valid_html_type(self):
        page = Page.objects.create(title="T", slug="type-html")
        comp = PageComponent(page=page, name="C", component_type="html", html_content="<p/>")
        comp.full_clean()

    def test_valid_markdown_type(self):
        page = Page.objects.create(title="T", slug="type-md")
        comp = PageComponent(page=page, name="C", component_type="markdown", html_content="<p/>")
        comp.full_clean()

    def test_valid_form_type(self):
        page = Page.objects.create(title="T", slug="type-form")
        form = UniformForm.objects.create(name="Contact", slug="contact")
        comp = PageComponent(page=page, name="C", component_type="form", html_content="", form=form)
        comp.full_clean()

    def test_valid_table_type(self):
        page = Page.objects.create(title="T", slug="type-table")
        comp = PageComponent(page=page, name="C", component_type="table", html_content="<table/>")
        comp.full_clean()

    def test_valid_google_sheet_type(self):
        page = Page.objects.create(title="T", slug="type-google-sheet")
        google_sheet = GoogleSheet.objects.create(
            name="Public Schedule",
            spreadsheet_id="spreadsheet-id",
            sheet_name="Sheet1",
        )
        comp = PageComponent(
            page=page,
            name="C",
            component_type="google_sheet",
            google_sheet=google_sheet,
        )
        comp.full_clean()

    def test_invalid_template_type_rejected(self):
        """The old 'template' type should be rejected by validation."""
        page = Page.objects.create(title="T", slug="type-tmpl")
        comp = PageComponent(page=page, name="C", component_type="template", html_content="<p/>")
        with self.assertRaises(ValidationError):
            comp.full_clean()

    def test_invalid_widget_type_rejected(self):
        """The old 'widget' type should be rejected by validation."""
        page = Page.objects.create(title="T", slug="type-widget")
        comp = PageComponent(page=page, name="C", component_type="widget", html_content="<p/>")
        with self.assertRaises(ValidationError):
            comp.full_clean()


class GoogleSheetComponentValidationTest(TestCase):
    def setUp(self):
        self.page = Page.objects.create(title="T", slug="google-sheet-validation")
        self.google_sheet = GoogleSheet.objects.create(
            name="Shared Sheet",
            spreadsheet_id="spreadsheet-id",
            sheet_name="Sheet1",
        )

    def test_google_sheet_component_requires_google_sheet_fk(self):
        comp = PageComponent(page=self.page, name="C", component_type="google_sheet")
        with self.assertRaises(ValidationError):
            comp.full_clean()

    def test_non_google_sheet_component_cannot_set_google_sheet_fk(self):
        comp = PageComponent(
            page=self.page,
            name="C",
            component_type="html",
            html_content="<p/>",
            google_sheet=self.google_sheet,
        )
        with self.assertRaises(ValidationError):
            comp.full_clean()

    def test_google_sheet_component_rejects_disabled_google_sheet(self):
        self.google_sheet.is_enabled = False
        self.google_sheet.save(update_fields=["is_enabled", "updated_at"])

        comp = PageComponent(
            page=self.page,
            name="C",
            component_type="google_sheet",
            google_sheet=self.google_sheet,
        )
        with self.assertRaises(ValidationError):
            comp.full_clean()
