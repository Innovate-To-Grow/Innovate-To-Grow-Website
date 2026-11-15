import uuid

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase

# Every page of the Delivery Operations tabs: Email Monitoring (each of its tabs and drill-downs), Notification
# Delivery and Delivery Rates. Email Monitoring → Amazon SES is the former Delivery Dashboard.
_SOME_ID = uuid.UUID(int=1)
DELIVERY_OPERATIONS_PATHS = (
    "/admin/mail/email-monitoring/",
    "/admin/mail/email-monitoring/emails/",
    f"/admin/mail/email-monitoring/emails/{_SOME_ID}/",
    "/admin/mail/email-monitoring/bounces/",
    f"/admin/mail/email-monitoring/campaigns/{_SOME_ID}/",
    "/admin/mail/email-monitoring/addresses/",
    f"/admin/mail/email-monitoring/addresses/{_SOME_ID}/",
    f"/admin/mail/email-monitoring/addresses/{_SOME_ID}/dismiss/",
    "/admin/mail/email-monitoring/ses/",
    "/admin/mail/settings/",
    "/admin/mail/settings/test-email/",
    "/admin/mail/settings/rates/",
)


class AdminSidebarNavigationTest(SimpleTestCase):
    def test_sidebar_navigation_starts_with_priority_groups(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        group_titles = [section["title"] for section in navigation]

        self.assertEqual(
            group_titles,
            [
                "Content Management System",
                "Events",
                "Projects",
                "Members & Authentication",
                "Broadcast Delivery",
                "Helpdesk",
                "System Intelligence",
                "Site Settings",
                "CLI Admin",
            ],
        )

    def test_sidebar_exposes_at_most_one_entry_for_each_tab_group(self):
        sidebar_links = []
        for section in settings.UNFOLD["SIDEBAR"]["navigation"]:
            for item in section["items"]:
                sidebar_links.append((section["title"], item["title"], item["link"]))

        for tab in settings.UNFOLD["TABS"]:
            tab_key = tab.get("page") or ", ".join(tab.get("models", []))
            tab_links = {item["link"] for item in tab["items"]}
            exposed_items = [
                (section_title, item_title, link)
                for section_title, item_title, link in sidebar_links
                if link in tab_links
            ]

            with self.subTest(tab=tab_key):
                self.assertLessEqual(
                    len(exposed_items),
                    1,
                    f"Tab group exposes multiple sidebar entries: {exposed_items}",
                )

    def test_site_settings_navigation_includes_core_entries(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        site_settings_section = next(section for section in navigation if section["title"] == "Site Settings")
        items_by_title = {item["title"]: item for item in site_settings_section["items"]}

        self.assertIn("Site Maintenance Control", items_by_title)
        self.assertIn("Service Credentials", items_by_title)
        self.assertNotIn("System Intelligence", items_by_title)
        self.assertEqual(items_by_title["Site Maintenance Control"]["link"], "/admin/core/sitemaintenancecontrol/")
        self.assertEqual(items_by_title["Service Credentials"]["link"], "/admin/core/awscredentialconfig/")
        self.assertEqual(items_by_title["Request Limits"]["link"], "/admin/core/request-limits/")
        self.assertNotIn("Service Configs", items_by_title)

    def test_content_navigation_prioritizes_editing_before_analytics(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        content_section = next(section for section in navigation if section["title"] == "Content Management System")
        items_by_title = {item["title"]: item for item in content_section["items"]}

        self.assertEqual(items_by_title["Page Content"]["link"], "/admin/cms/cmspage/")
        self.assertEqual(items_by_title["Route Redirects"]["link"], "/admin/cms/routeredirect/")
        self.assertEqual(items_by_title["News Management"]["link"], "/admin/cms/newsarticle/")
        self.assertEqual(items_by_title["Page Analytics"]["link"], "/admin/cms/pageview/")

    def test_events_and_projects_navigation_keeps_existing_names(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        events_section = next(section for section in navigation if section["title"] == "Events")
        projects_section = next(section for section in navigation if section["title"] == "Projects")
        event_items_by_title = {item["title"]: item for item in events_section["items"]}
        project_items_by_title = {item["title"]: item for item in projects_section["items"]}

        self.assertEqual(event_items_by_title["Events & Registrations"]["link"], "/admin/event/event/")
        self.assertEqual(
            event_items_by_title["Current Projects & Schedule"]["link"], "/admin/event/currentprojectschedule/"
        )
        self.assertEqual(project_items_by_title["Projects"]["link"], "/admin/projects/project/")
        self.assertEqual(
            project_items_by_title["Project Resources"]["link"], "/admin/projects/pastprojectssheetconfig/"
        )
        self.assertNotIn("Past Projects", project_items_by_title)
        self.assertNotIn("Past Projects Sheet", project_items_by_title)
        self.assertNotIn("Semesters", project_items_by_title)

    def test_project_pages_are_grouped_under_project_tabs(self):
        tabs = settings.UNFOLD["TABS"]
        projects_tab = next(tab for tab in tabs if "projects.project" in tab.get("models", []))
        project_resources_tab = next(tab for tab in tabs if "projects.pastprojectssheetconfig" in tab.get("models", []))

        self.assertEqual(projects_tab["models"], ["projects.project", "projects.semester"])
        self.assertEqual(
            projects_tab["items"],
            [
                {"title": "Projects", "link": "/admin/projects/project/"},
                {"title": "Semesters", "link": "/admin/projects/semester/"},
            ],
        )
        self.assertEqual(
            project_resources_tab["models"],
            [
                "projects.pastprojectssheetconfig",
                "projects.pastprojectshare",
                "projects.pastprojectsynclog",
            ],
        )
        self.assertEqual(
            project_resources_tab["items"],
            [
                {"title": "Project Resources", "link": "/admin/projects/pastprojectssheetconfig/"},
                {"title": "Shared Links", "link": "/admin/projects/pastprojectshare/"},
                {"title": "Project Resource Sync Logs", "link": "/admin/projects/pastprojectsynclog/"},
            ],
        )

    def test_system_intelligence_navigation_includes_chat_and_settings(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        system_intelligence_section = next(
            section for section in navigation if section["title"] == "System Intelligence"
        )
        items_by_title = {item["title"]: item for item in system_intelligence_section["items"]}

        self.assertEqual(items_by_title["Chat"]["link"], "/admin/system-intelligence/")
        self.assertEqual(
            items_by_title["Assistant Tools"]["link"],
            "/admin/system_intelligence/systemintelligenceconfig/",
        )
        self.assertNotIn("Assistant Settings", items_by_title)
        self.assertNotIn("Usage Dashboard", items_by_title)
        self.assertNotIn("Conversation Logs", items_by_title)

    def test_system_intelligence_chat_sidebar_active_state_is_exact(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        system_intelligence_section = next(
            section for section in navigation if section["title"] == "System Intelligence"
        )
        items_by_title = {item["title"]: item for item in system_intelligence_section["items"]}
        factory = RequestFactory()

        chat_request = factory.get("/admin/system-intelligence/")
        usage_request = factory.get("/admin/system-intelligence/usage/")

        self.assertTrue(items_by_title["Chat"]["active"](chat_request))
        self.assertFalse(items_by_title["Chat"]["active"](usage_request))
