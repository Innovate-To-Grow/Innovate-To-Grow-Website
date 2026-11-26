import re
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.services.aws.credentials import AwsCredentialsError
from apps.event.tests.helpers import make_superuser


class _AdminIndexNavigationCase(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")


class AdminIndexNavigationTest(_AdminIndexNavigationCase):
    def test_admin_index_uses_sidebar_navigation_groups(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/index.html")
        self.assertContains(response, "Content Management System")
        self.assertContains(response, "Page Content")
        self.assertContains(response, "Site Settings")
        self.assertContains(response, "Site Maintenance Control")
        self.assertContains(response, "Page Analytics")
        self.assertContains(response, 'href="/admin/system-intelligence/"')
        self.assertNotContains(response, "Models in the Administration application")

    def test_members_and_sheet_sync_render_as_admin_tabs(self):
        for url, active_href in (
            (reverse("admin:authn_member_changelist"), "/admin/authn/member/"),
            (reverse("admin:authn_membersheetsyncconfig_changelist"), "/admin/authn/membersheetsyncconfig/"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="tabs-items"')
                self.assertContains(response, 'href="/admin/authn/member/"')
                self.assertContains(response, 'href="/admin/authn/membersheetsyncconfig/"')
                self.assertContains(response, 'href="/admin/authn/membersheetsynclog/"')
                self.assertContains(response, 'href="/admin/authn/memberimportbatch/"')
                self.assertContains(response, f'href="{active_href}" class="active"')

        response = self.client.get(reverse("admin:authn_member_changelist"))
        html = response.content.decode()
        sidebar_html = html.split('<div id="main"', maxsplit=1)[0]
        self.assertNotIn("Member Sheet Sync", sidebar_html)

    # Email Monitoring → Amazon SES reads AWS: here both clients report "not configured", without a network.
    @patch("apps.mail.services.campaign.dashboard._sesv2_client", side_effect=AwsCredentialsError("not configured"))
    @patch(
        "apps.mail.services.campaign.dashboard._cloudwatch_client", side_effect=AwsCredentialsError("not configured")
    )
    def test_mail_delivery_operations_render_as_admin_tabs(self, _cloudwatch, _sesv2):
        monitoring = "/admin/mail/email-monitoring/"
        for url, active_href in (
            (reverse("admin:mail_email_monitoring"), monitoring),
            (reverse("admin:mail_email_monitoring_emails"), monitoring),
            (reverse("admin:mail_email_monitoring_bounces"), monitoring),
            (reverse("admin:mail_email_monitoring_addresses"), monitoring),
            (reverse("admin:mail_email_monitoring_ses"), monitoring),
            (reverse("admin:mail_settings"), "/admin/mail/settings/"),
            (reverse("admin:mail_delivery_rates"), "/admin/mail/settings/rates/"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="tabs-items"')
                self.assertContains(response, 'href="/admin/mail/email-monitoring/"')
                self.assertContains(response, 'href="/admin/mail/settings/"')
                self.assertContains(response, 'href="/admin/mail/settings/rates/"')
                self.assertNotContains(response, 'href="/admin/mail/delivery-dashboard/"')
                self.assertContains(response, f'href="{active_href}" class="active"')
                self.assertContains(response, 'class="active"', count=1)

        response = self.client.get(reverse("admin:mail_email_monitoring_ses"))
        html = response.content.decode()
        sidebar_html = html.split('<div id="main"', maxsplit=1)[0]
        broadcast_sidebar_html = sidebar_html.rsplit("Broadcast Delivery", maxsplit=1)[-1].split(
            "System Intelligence", maxsplit=1
        )[0]
        self.assertIn("Delivery Operations", broadcast_sidebar_html)
        self.assertNotIn("Delivery Status & Settings", broadcast_sidebar_html)
        self.assertNotIn("Delivery Dashboard", broadcast_sidebar_html)
        self.assertNotIn("Notification Delivery", broadcast_sidebar_html)

    def test_email_sending_method_is_the_only_highlighted_broadcast_entry_on_its_pages(self):
        # Unfold also highlights an entry when any tab of its group matches the path, so a page under
        # /admin/mail/settings/ would light up Delivery Operations too; this renders the real sidebar.
        def sidebar_link_classes(url):
            html = self.client.get(url).content.decode().split('<div id="main"', maxsplit=1)[0]
            return dict(re.findall(r'<a href="(/admin/mail/[^"]*)" class="([^"]*)"', html))

        for url in (
            reverse("admin:mail_sending_method"),
            reverse("admin:mail_settings_test_email_provider", args=["ses"]),
        ):
            with self.subTest(url=url):
                classes = sidebar_link_classes(url)
                self.assertIn("font-semibold", classes["/admin/mail/sending-method/"])
                self.assertNotIn("font-semibold", classes["/admin/mail/email-monitoring/"])

        for url in (reverse("admin:mail_settings"), reverse("admin:mail_email_monitoring")):
            with self.subTest(url=url):
                classes = sidebar_link_classes(url)
                self.assertIn("font-semibold", classes["/admin/mail/email-monitoring/"])
                self.assertNotIn("font-semibold", classes["/admin/mail/sending-method/"])

    def test_projects_and_semesters_render_as_admin_tabs(self):
        for url, active_href in (
            (reverse("admin:projects_project_changelist"), "/admin/projects/project/"),
            (reverse("admin:projects_semester_changelist"), "/admin/projects/semester/"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="tabs-items"')
                self.assertContains(response, 'href="/admin/projects/project/"')
                self.assertContains(response, 'href="/admin/projects/semester/"')
                self.assertContains(response, f'href="{active_href}" class="active"')

        response = self.client.get(reverse("admin:projects_project_changelist"))
        html = response.content.decode()
        sidebar_html = html.split('<div id="main"', maxsplit=1)[0]
        self.assertNotIn("Semesters", sidebar_html)

    def test_project_resource_models_render_as_admin_tabs(self):
        for url, active_href in (
            (reverse("admin:projects_pastprojectssheetconfig_changelist"), "/admin/projects/pastprojectssheetconfig/"),
            (reverse("admin:projects_pastprojectsynclog_changelist"), "/admin/projects/pastprojectsynclog/"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="tabs-items"')
                self.assertContains(response, 'href="/admin/projects/pastprojectssheetconfig/"')
                self.assertContains(response, 'href="/admin/projects/pastprojectsynclog/"')
                self.assertContains(response, f'href="{active_href}" class="active"')

    def test_system_intelligence_log_pages_render_as_admin_tabs(self):
        tab_links = (
            "/admin/system-intelligence/usage/",
            "/admin/system_intelligence/assistantconversationlog/",
            "/admin/system_intelligence/assistantmessagelog/",
            "/admin/system_intelligence/systemintelligenceactionrequest/",
        )
        for url, active_href in (
            (reverse("admin:system_intelligence_assistantconversationlog_changelist"), tab_links[1]),
            (reverse("admin:system_intelligence_assistantmessagelog_changelist"), tab_links[2]),
            (reverse("admin:system_intelligence_systemintelligenceactionrequest_changelist"), tab_links[3]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="tabs-items"')
                for link in tab_links:
                    self.assertContains(response, f'href="{link}"')
                self.assertContains(response, f'href="{active_href}" class="active"')

        response = self.client.get(reverse("admin:system_intelligence_assistantconversationlog_changelist"))
        sidebar_html = response.content.decode().split('<div id="main"', maxsplit=1)[0]
        self.assertIn("<span>Usage & Logs</span>", sidebar_html)
        self.assertIn("AI Providers", sidebar_html)
        self.assertNotIn("Conversation Logs", sidebar_html)
        self.assertNotIn("Message Logs", sidebar_html)

    def test_system_intelligence_configuration_pages_have_no_tab_bar(self):
        for name in ("systemintelligenceconfig", "llmproviderconfig"):
            with self.subTest(model=name):
                response = self.client.get(reverse(f"admin:system_intelligence_{name}_changelist"))

                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'id="tabs-items"')
