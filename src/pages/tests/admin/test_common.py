"""
Tests for shared admin functionality: WorkflowAdminMixin,
CompactComponentInline, and PageComponentAdmin.

Covers:
- WorkflowAdminMixin shared behavior (display names, component counts, badges, save_model)
- CompactComponentInline configuration
"""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from ...admin.content.home_page import HomePageAdmin
from ...admin.content.page import PageAdmin
from ...admin.shared.base import CompactComponentInline
from ...models import HomePage, Page, PageComponent, PageComponentPlacement

User = get_user_model()


class WorkflowAdminMixinTest(TestCase):
    """Test the shared WorkflowAdminMixin used by both PageAdmin and HomePageAdmin."""

    def setUp(self):
        self.site = AdminSite()

    def test_page_admin_get_display_name(self):
        """PageAdmin.get_display_name returns obj.title."""
        page_admin = PageAdmin(Page, self.site)
        page = Page.objects.create(title="My Page", slug="display-name")
        self.assertEqual(page_admin.get_display_name(page), "My Page")

    def test_homepage_admin_get_display_name(self):
        """HomePageAdmin.get_display_name returns obj.name."""
        hp_admin = HomePageAdmin(HomePage, self.site)
        hp = HomePage.objects.create(name="My Home")
        self.assertEqual(hp_admin.get_display_name(hp), "My Home")

    def test_component_count_page(self):
        page_admin = PageAdmin(Page, self.site)
        page = Page.objects.create(title="T", slug="comp-count")
        c1 = PageComponent.objects.create(name="C1", component_type="html", html_content="<p/>")
        c2 = PageComponent.objects.create(name="C2", component_type="html", html_content="<p/>")
        PageComponentPlacement.objects.create(component=c1, page=page, order=1)
        PageComponentPlacement.objects.create(component=c2, page=page, order=2)
        self.assertEqual(page_admin.component_count(page), 2)

    def test_component_count_homepage(self):
        hp_admin = HomePageAdmin(HomePage, self.site)
        hp = HomePage.objects.create(name="HP Count")
        c1 = PageComponent.objects.create(name="C1", component_type="html", html_content="<p/>")
        PageComponentPlacement.objects.create(component=c1, home_page=hp, order=1)
        self.assertEqual(hp_admin.component_count(hp), 1)

    def test_status_badge_draft(self):
        page_admin = PageAdmin(Page, self.site)
        page = Page.objects.create(title="T", slug="badge-draft2")
        badge = page_admin.status_badge(page)
        self.assertIn("Draft", badge)
        self.assertIn("#6c757d", badge)

    def test_status_badge_review(self):
        page_admin = PageAdmin(Page, self.site)
        page = Page.objects.create(title="T", slug="badge-review2", status="review")
        badge = page_admin.status_badge(page)
        self.assertIn("Pending Publish", badge)
        self.assertIn("#f0ad4e", badge)

    def test_status_badge_published(self):
        page_admin = PageAdmin(Page, self.site)
        page = Page.objects.create(title="T", slug="badge-pub2", status="published")
        badge = page_admin.status_badge(page)
        self.assertIn("Published", badge)
        self.assertIn("#5cb85c", badge)

    def test_save_model_creates_version_on_edit(self):
        """save_model creates a version record on edit (change=True)."""
        page_admin = PageAdmin(Page, self.site)
        page = Page.objects.create(title="T", slug="save-model-ver")
        factory = RequestFactory()
        request = factory.post("/admin/pages/page/")
        request.user = User.objects.create_superuser(username="admin_save", password="admin123", email="save@test.com")

        initial_count = len(page.get_versions())
        page_admin.save_model(request, page, form=None, change=True)

        versions = page.get_versions()
        self.assertGreater(len(versions), initial_count)
        self.assertIn("Edited via admin", versions[0].comment)

    def test_save_model_no_version_on_create(self):
        """save_model does NOT create version on initial creation (change=False)."""
        page_admin = PageAdmin(Page, self.site)
        page = Page.objects.create(title="T", slug="save-model-new")
        factory = RequestFactory()
        request = factory.post("/admin/pages/page/")
        request.user = User.objects.create_superuser(username="admin_new", password="admin123", email="new@test.com")

        initial_count = len(page.get_versions())
        page_admin.save_model(request, page, form=None, change=False)
        self.assertEqual(len(page.get_versions()), initial_count)


class CompactComponentInlineTest(TestCase):
    """Test CompactComponentInline configuration."""

    def test_inline_fields(self):
        """Verify that inline fields include component and order for placement management."""
        self.assertEqual(
            CompactComponentInline.fields,
            (
                "component",
                "order",
            ),
        )

    def test_inline_extra_is_zero(self):
        self.assertEqual(CompactComponentInline.extra, 0)

    def test_inline_show_change_link(self):
        self.assertTrue(CompactComponentInline.show_change_link)

    def test_inline_model(self):
        self.assertEqual(CompactComponentInline.model, PageComponentPlacement)
