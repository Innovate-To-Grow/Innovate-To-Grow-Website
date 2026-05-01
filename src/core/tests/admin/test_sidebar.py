from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from event.tests.helpers import make_superuser


class AdminSidebarNavigationTest(SimpleTestCase):
    def test_site_settings_navigation_includes_core_entries(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        site_settings_section = next(section for section in navigation if section["title"] == "Site Settings")
        item_titles = {item["title"] for item in site_settings_section["items"]}

        self.assertIn("Site Maintenance Control", item_titles)
        self.assertIn("Service Configs", item_titles)

    def test_members_navigation_includes_auth_entries(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        members_section = next(section for section in navigation if section["title"] == "Members & Authentication")
        item_titles = {item["title"] for item in members_section["items"]}

        self.assertIn("Members", item_titles)
        self.assertIn("Contact Info", item_titles)
        self.assertIn("Admin Invitations", item_titles)

    def test_service_config_tabs_include_gmail_import(self):
        tabs = settings.UNFOLD["TABS"]
        service_config_tab = next(tab for tab in tabs if "core.gmailimportconfig" in tab["models"])
        item_titles = {item["title"] for item in service_config_tab["items"]}

        self.assertIn("Email Config", item_titles)
        self.assertIn("Gmail Import", item_titles)
        self.assertIn("SMS Config", item_titles)
        self.assertIn("Google Credentials", item_titles)


class AdminIndexNavigationTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_admin_index_uses_sidebar_navigation_groups(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/index.html")
        self.assertContains(response, "Site Settings")
        self.assertContains(response, "Site Maintenance Control")
        self.assertContains(response, "Content Management System")
        self.assertContains(response, "Page Analytics")
        self.assertContains(response, 'href="/admin/core/system-intelligence/"')
        self.assertNotContains(response, "Models in the Administration application")
