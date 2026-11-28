from types import SimpleNamespace

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.core.tests.admin.navigation.test_sidebar import DELIVERY_OPERATIONS_PATHS


class AdminSidebarNavigationTest(SimpleTestCase):
    def test_system_intelligence_usage_pages_are_grouped_under_usage_tabs(self):
        tabs = settings.UNFOLD["TABS"]
        model_tab = next(tab for tab in tabs if "system_intelligence.assistantconversationlog" in tab.get("models", []))
        page_tab = next(tab for tab in tabs if tab.get("page") == "system_intelligence_usage")

        expected_items = [
            {"title": "Usage Dashboard", "link": "/admin/system-intelligence/usage/"},
            {"title": "Conversation Logs", "link": "/admin/system_intelligence/assistantconversationlog/"},
            {"title": "Message Logs", "link": "/admin/system_intelligence/assistantmessagelog/"},
            {"title": "Action Requests", "link": "/admin/system_intelligence/systemintelligenceactionrequest/"},
        ]

        self.assertEqual(
            model_tab["models"],
            [
                "system_intelligence.assistantconversationlog",
                "system_intelligence.assistantmessagelog",
                "system_intelligence.systemintelligenceactionrequest",
            ],
        )
        self.assertEqual(model_tab["items"], expected_items)
        self.assertEqual(page_tab["items"], expected_items)

    def test_system_intelligence_configuration_pages_are_not_tabbed(self):
        tabbed_models = {
            model if isinstance(model, str) else model["name"]
            for tab in settings.UNFOLD["TABS"]
            for model in tab.get("models", [])
        }

        self.assertNotIn("system_intelligence.systemintelligenceconfig", tabbed_models)
        self.assertNotIn("system_intelligence.llmproviderconfig", tabbed_models)

    def test_members_navigation_includes_auth_entries(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        members_section = next(section for section in navigation if section["title"] == "Members & Authentication")
        item_titles = {item["title"] for item in members_section["items"]}

        self.assertIn("Members", item_titles)
        self.assertIn("Emails & Phones", item_titles)
        self.assertIn("Admin Invitations", item_titles)
        self.assertNotIn("Emails", item_titles)
        self.assertNotIn("Phones", item_titles)
        self.assertNotIn("Member Sheet Sync", item_titles)
        self.assertNotIn("Contact Info", item_titles)

    def test_member_sheet_sync_is_grouped_under_members_tabs(self):
        tabs = settings.UNFOLD["TABS"]
        members_tab = next(tab for tab in tabs if "authn.member" in tab.get("models", []))
        item_titles = {item["title"] for item in members_tab["items"]}
        item_links = {item["title"]: item["link"] for item in members_tab["items"]}

        self.assertEqual(
            members_tab["models"],
            ["authn.member", "authn.membersheetsyncconfig", "authn.membersheetsynclog", "authn.memberimportbatch"],
        )
        self.assertEqual(item_titles, {"Members", "Member Sheet Sync", "Sync Logs", "Member Imports"})
        self.assertEqual(item_links["Members"], "/admin/authn/member/")
        self.assertEqual(item_links["Member Sheet Sync"], "/admin/authn/membersheetsyncconfig/")
        self.assertEqual(item_links["Sync Logs"], "/admin/authn/membersheetsynclog/")
        self.assertEqual(item_links["Member Imports"], "/admin/authn/memberimportbatch/")

    def test_mail_navigation_includes_settings_and_tools(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        mail_section = next(section for section in navigation if section["title"] == "Broadcast Delivery")
        items_by_title = {item["title"]: item for item in mail_section["items"]}

        self.assertEqual(items_by_title["Delivery Operations"]["link"], "/admin/mail/email-monitoring/")
        self.assertEqual(items_by_title["Email Sending Method"]["link"], "/admin/mail/sending-method/")
        self.assertEqual(items_by_title["Inbox"]["link"], "/admin/mail/inbox/")
        self.assertEqual(items_by_title["Inbox"]["badge"], "apps.mail.admin.inbox.badge.inbox_unread_badge")
        self.assertEqual(items_by_title["Broadcast Campaigns"]["link"], "/admin/mail/emailcampaign/")
        self.assertNotIn("Delivery Status & Settings", items_by_title)
        self.assertNotIn("Delivery Dashboard", items_by_title)
        self.assertNotIn("Email Monitoring", items_by_title)
        self.assertNotIn("Notification Delivery", items_by_title)
        self.assertNotIn("Broadcast Email", items_by_title)
        self.assertNotIn("Broadcast SMS", items_by_title)
        self.assertNotIn("Scam Detection", items_by_title)

    def test_mail_delivery_operations_sidebar_is_active_on_every_delivery_page(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        mail_section = next(section for section in navigation if section["title"] == "Broadcast Delivery")
        items_by_title = {item["title"]: item for item in mail_section["items"]}
        factory = RequestFactory()

        for path in DELIVERY_OPERATIONS_PATHS:
            self.assertTrue(items_by_title["Delivery Operations"]["active"](factory.get(path)), path)
        # The old Delivery Dashboard address renders nothing (it redirects to Email Monitoring → Amazon SES).
        for path in ("/admin/mail/inbox/", "/admin/mail/emailcampaign/", "/admin/mail/delivery-dashboard/"):
            self.assertFalse(items_by_title["Delivery Operations"]["active"](factory.get(path)), path)
        # Email Sending Method has its own entry: it, not Delivery Operations, is highlighted on its pages.
        for path in (
            "/admin/mail/sending-method/",
            "/admin/mail/sending-method/smtp/test-email/",
            "/admin/mail/sending-method/smtp/use/",
        ):
            self.assertTrue(items_by_title["Email Sending Method"]["active"](factory.get(path)), path)
            self.assertFalse(items_by_title["Delivery Operations"]["active"](factory.get(path)), path)
        for path in ("/admin/mail/settings/", "/admin/mail/settings/test-email/", "/admin/mail/settings/rates/"):
            self.assertFalse(items_by_title["Email Sending Method"]["active"](factory.get(path)), path)

    def test_mail_delivery_operations_pages_are_grouped_under_tabs(self):
        tabs = settings.UNFOLD["TABS"]
        delivery_tab = next(tab for tab in tabs if tab.get("page") == "mail_delivery_operations")

        self.assertEqual(
            [{key: item[key] for key in ("title", "link")} for item in delivery_tab["items"]],
            [
                {"title": "Email Monitoring", "link": "/admin/mail/email-monitoring/"},
                {"title": "Notification Delivery", "link": "/admin/mail/settings/"},
                {"title": "Delivery Rates", "link": "/admin/mail/settings/rates/"},
            ],
        )

    def test_service_config_tabs_exclude_standalone_mail_settings(self):
        tabs = settings.UNFOLD["TABS"]
        service_config_tab = next(tab for tab in tabs if "core.gmailaccessaccount" in tab["models"])
        item_titles = {item["title"] for item in service_config_tab["items"]}

        self.assertNotIn("system_intelligence.systemintelligenceconfig", service_config_tab["models"])
        self.assertNotIn("core.emailserviceconfig", service_config_tab["models"])
        self.assertNotIn("core.smsserviceconfig", service_config_tab["models"])
        self.assertNotIn("System Intelligence Config", item_titles)
        self.assertNotIn("Notification Delivery", item_titles)
        self.assertIn("Gmail IMAP (Template Import)", item_titles)
        self.assertNotIn("SMS Config", item_titles)
        self.assertIn("Google Credentials", item_titles)
        self.assertIn("AWS Credentials", item_titles)
        self.assertIn("core.sendverificationconfig", service_config_tab["models"])
        self.assertIn("Send Verification", item_titles)

    def test_service_credentials_tabs_list_every_email_provider(self):
        tab = next(tab for tab in settings.UNFOLD["TABS"] if "core.awscredentialconfig" in tab["models"])
        links = {item["title"]: item["link"] for item in tab["items"]}

        self.assertEqual(
            list(links),
            [
                "AWS Credentials",
                "SMTP",
                "Microsoft Graph",
                "Graph Access Checks",
                "Gmail API",
                "Gmail IMAP (Template Import)",
                "Google Credentials",
                "Send Verification",
            ],
        )
        for title, url_name in (
            ("SMTP", "admin:core_smtpproviderconfig_changelist"),
            ("Microsoft Graph", "admin:core_microsoftgraphproviderconfig_changelist"),
            ("Graph Access Checks", "admin:core_microsoftgraphaccesscheck_changelist"),
            ("Gmail API", "admin:core_gmailapiproviderconfig_changelist"),
        ):
            self.assertEqual(links[title], reverse(url_name))
        # Every tab's pages show the tab bar.
        for model in ("core.smtpproviderconfig", "core.microsoftgraphproviderconfig", "core.gmailapiproviderconfig"):
            self.assertIn(model, tab["models"])

    def test_the_gmail_api_tab_is_shown_like_the_other_service_credentials(self):
        # The Gmail API config is open to every Admin like its neighbours, so its tab has no extra permission.
        tab = next(tab for tab in settings.UNFOLD["TABS"] if "core.awscredentialconfig" in tab["models"])
        [gmail_api] = [item for item in tab["items"] if item["title"] == "Gmail API"]
        [graph] = [item for item in tab["items"] if item["title"] == "Microsoft Graph"]

        self.assertNotIn("permission", gmail_api)
        self.assertEqual(gmail_api.keys(), graph.keys())

    def test_service_credentials_stays_highlighted_on_every_credential_tab(self):
        site_settings = next(
            group for group in settings.UNFOLD["SIDEBAR"]["navigation"] if group["title"] == "Site Settings"
        )
        [item] = [item for item in site_settings["items"] if item["title"] == "Service Credentials"]

        for path in ("/admin/core/microsoftgraphproviderconfig/", "/admin/core/smtpproviderconfig/1/change/"):
            self.assertTrue(item["active"](SimpleNamespace(path=path)), path)
        self.assertFalse(item["active"](SimpleNamespace(path="/admin/core/sitemaintenancecontrol/")))
