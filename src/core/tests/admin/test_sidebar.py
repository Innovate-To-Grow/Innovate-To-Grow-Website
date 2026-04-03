from django.conf import settings
from django.test import SimpleTestCase


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
