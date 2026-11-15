from django.conf import settings
from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse


class AdminSidebarNavigationTest(SimpleTestCase):
    def test_mail_settings_route_is_registered_under_mail_app(self):
        self.assertEqual(reverse("admin:mail_email_monitoring_ses"), "/admin/mail/email-monitoring/ses/")
        self.assertEqual(reverse("admin:mail_email_monitoring_ses_data"), "/admin/mail/email-monitoring/ses/data/")
        # The Delivery Dashboard's names still reverse (the page redirects, the JSON still answers).
        self.assertEqual(reverse("admin:mail_delivery_dashboard"), "/admin/mail/delivery-dashboard/")
        self.assertEqual(reverse("admin:mail_delivery_dashboard_data"), "/admin/mail/delivery-dashboard/data/")
        self.assertEqual(reverse("admin:mail_settings"), "/admin/mail/settings/")
        self.assertEqual(reverse("admin:mail_smscampaign_changelist"), "/admin/mail/smscampaign/")
        with self.assertRaises(NoReverseMatch):
            reverse("admin:core_emailserviceconfig_changelist")
        with self.assertRaises(NoReverseMatch):
            reverse("admin:mail_scamdetectorconfig_changelist")

    def test_cli_admin_navigation_uses_access_and_audit_group_entry(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        cli_admin_section = next(section for section in navigation if section["title"] == "CLI Admin")
        items_by_title = {item["title"]: item for item in cli_admin_section["items"]}

        self.assertEqual(items_by_title["CLI Access & Audit"]["link"], "/admin/cli_admin/cliaccesstoken/")
        self.assertNotIn("Access & Audit", items_by_title)
        self.assertNotIn("Access Tokens", items_by_title)
        self.assertNotIn("Authorization Codes", items_by_title)
        self.assertNotIn("Audit Log", items_by_title)

    def test_cli_admin_pages_are_grouped_under_access_token_tabs(self):
        tabs = settings.UNFOLD["TABS"]
        cli_admin_tab = next(tab for tab in tabs if "cli_admin.cliaccesstoken" in tab.get("models", []))

        self.assertEqual(
            cli_admin_tab["models"],
            [
                "cli_admin.cliaccesstoken",
                "cli_admin.cliauthorizationcode",
                "cli_admin.cliauditlog",
            ],
        )
        self.assertEqual(
            cli_admin_tab["items"],
            [
                {"title": "Access Tokens", "link": "/admin/cli_admin/cliaccesstoken/"},
                {"title": "Authorization Codes", "link": "/admin/cli_admin/cliauthorizationcode/"},
                {"title": "Audit Log", "link": "/admin/cli_admin/cliauditlog/"},
            ],
        )
