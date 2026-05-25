from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import NoReverseMatch, reverse

from event.tests.helpers import make_superuser


class AdminSidebarNavigationTest(SimpleTestCase):
    def test_sidebar_navigation_starts_with_priority_groups(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        group_titles = [section["title"] for section in navigation]

        self.assertEqual(
            group_titles[:4],
            [
                "Site Settings",
                "Content Management System",
                "Members & Authentication",
                "Amazon SES Email & Gmail",
            ],
        )

    def test_site_settings_navigation_includes_core_entries(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        site_settings_section = next(section for section in navigation if section["title"] == "Site Settings")
        items_by_title = {item["title"]: item for item in site_settings_section["items"]}

        self.assertIn("Site Maintenance Control", items_by_title)
        self.assertIn("Service Configs", items_by_title)
        self.assertNotIn("System Intelligence", items_by_title)
        self.assertEqual(items_by_title["Service Configs"]["link"], "/admin/core/awscredentialconfig/")

    def test_system_intelligence_navigation_includes_chat_and_settings(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        system_intelligence_section = next(
            section for section in navigation if section["title"] == "System Intelligence"
        )
        items_by_title = {item["title"]: item for item in system_intelligence_section["items"]}

        self.assertEqual(items_by_title["System Intelligence"]["link"], "/admin/system-intelligence/")
        self.assertEqual(
            items_by_title["System Intelligence settings"]["link"],
            "/admin/system_intelligence/systemintelligenceconfig/",
        )

    def test_members_navigation_includes_auth_entries(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        members_section = next(section for section in navigation if section["title"] == "Members & Authentication")
        item_titles = {item["title"] for item in members_section["items"]}

        self.assertIn("Members", item_titles)
        self.assertIn("Contact Info", item_titles)
        self.assertIn("Admin Invitations", item_titles)

    def test_mail_navigation_includes_settings_and_tools(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        mail_section = next(section for section in navigation if section["title"] == "Amazon SES Email & Gmail")
        items_by_title = {item["title"]: item for item in mail_section["items"]}

        self.assertEqual(items_by_title["Mail Settings"]["link"], "/admin/mail/settings/")
        self.assertEqual(items_by_title["Gmail"]["link"], "/admin/mail/inbox/")
        self.assertEqual(items_by_title["Broadcast Email"]["link"], "/admin/mail/emailcampaign/")

    def test_service_config_tabs_exclude_standalone_mail_settings(self):
        tabs = settings.UNFOLD["TABS"]
        service_config_tab = next(tab for tab in tabs if "core.gmailaccessaccount" in tab["models"])
        item_titles = {item["title"] for item in service_config_tab["items"]}

        self.assertNotIn("system_intelligence.systemintelligenceconfig", service_config_tab["models"])
        self.assertNotIn("core.emailserviceconfig", service_config_tab["models"])
        self.assertNotIn("core.smsserviceconfig", service_config_tab["models"])
        self.assertNotIn("System Intelligence Config", item_titles)
        self.assertNotIn("Mail Settings", item_titles)
        self.assertIn("Gmail Access Account", item_titles)
        self.assertNotIn("SMS Config", item_titles)
        self.assertIn("Google Credentials", item_titles)
        self.assertIn("AWS Credentials", item_titles)

    def test_mail_settings_route_is_registered_under_mail_app(self):
        self.assertEqual(reverse("admin:mail_settings"), "/admin/mail/settings/")
        with self.assertRaises(NoReverseMatch):
            reverse("admin:core_emailserviceconfig_changelist")


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
        self.assertContains(response, 'href="/admin/system-intelligence/"')
        self.assertNotContains(response, "Models in the Administration application")
