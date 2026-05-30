"""Tests for the Menu and FooterContent admin: editor context, items_count, save_model defaults."""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.cms.admin.layout.footer_content import FooterContentAdmin
from apps.cms.admin.layout.menu import MenuAdmin
from apps.cms.models import FooterContent, Menu

Member = get_user_model()


class MenuAdminUnitTests(TestCase):
    def setUp(self):
        self.admin = MenuAdmin(Menu, AdminSite())

    def test_get_editor_context_returns_route_editor_payload(self):
        context = self.admin._get_editor_context()
        self.assertIn("app_routes_json", context)
        self.assertIn("cms_routes_json", context)

    def test_items_count_empty(self):
        menu = Menu(name="empty_nav", items=[])
        self.assertEqual(self.admin.items_count(menu), 0)

    def test_items_count_none(self):
        menu = Menu(name="none_nav", items=None)
        self.assertEqual(self.admin.items_count(menu), 0)

    def test_items_count_counts_nested_children(self):
        items = [
            {"label": "Home", "children": []},
            {
                "label": "About",
                "children": [
                    {"label": "Team", "children": []},
                    {"label": "History", "children": [{"label": "1900s"}]},
                ],
            },
        ]
        menu = Menu(name="deep_nav", items=items)
        # 2 top-level + 2 children of About + 1 grandchild = 5.
        self.assertEqual(self.admin.items_count(menu), 5)

    def test_save_model_autopopulates_display_name_from_name(self):
        request = RequestFactory().post("/admin/cms/menu/add/")
        menu = Menu(name="main_nav", display_name="")
        self.admin.save_model(request, menu, form=None, change=False)
        menu.refresh_from_db()
        self.assertEqual(menu.display_name, "Main Nav")

    def test_save_model_preserves_existing_display_name(self):
        request = RequestFactory().post("/admin/cms/menu/add/")
        menu = Menu(name="footer_nav", display_name="Custom Footer")
        self.admin.save_model(request, menu, form=None, change=False)
        menu.refresh_from_db()
        self.assertEqual(menu.display_name, "Custom Footer")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class MenuAdminViewTests(TestCase):
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(password="testpass123", first_name="Menu", last_name="Admin")
        ContactEmail.objects.create(
            member=self.admin_user, email_address="menu-admin@example.com", email_type="primary", verified=True
        )
        self.client.login(username="menu-admin@example.com", password="testpass123")

    def test_add_view_injects_editor_context(self):
        response = self.client.get(reverse("admin:cms_menu_add"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("app_routes_json", response.context)

    def test_change_view_injects_editor_context(self):
        menu = Menu.objects.create(name="primary_nav", display_name="Primary", items=[])
        response = self.client.get(reverse("admin:cms_menu_change", args=[menu.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("cms_routes_json", response.context)


class FooterContentAdminUnitTests(TestCase):
    def setUp(self):
        self.admin = FooterContentAdmin(FooterContent, AdminSite())

    def test_get_editor_context_returns_route_editor_payload(self):
        context = self.admin._get_editor_context()
        self.assertIn("app_routes_json", context)
        self.assertIn("cms_routes_json", context)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class FooterContentAdminViewTests(TestCase):
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            password="testpass123", first_name="Footer", last_name="Admin"
        )
        ContactEmail.objects.create(
            member=self.admin_user, email_address="footer-admin@example.com", email_type="primary", verified=True
        )
        self.client.login(username="footer-admin@example.com", password="testpass123")

    def test_add_view_injects_editor_context(self):
        response = self.client.get(reverse("admin:cms_footercontent_add"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("app_routes_json", response.context)

    def test_change_view_injects_editor_context(self):
        footer = FooterContent.objects.create(name="Main Footer", slug="main-footer", content={}, is_active=True)
        response = self.client.get(reverse("admin:cms_footercontent_change", args=[footer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("cms_routes_json", response.context)
