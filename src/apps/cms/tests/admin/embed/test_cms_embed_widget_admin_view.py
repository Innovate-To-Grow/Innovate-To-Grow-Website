from django.test import TestCase
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.cms.models import CMSBlock, CMSEmbedWidget, CMSPage
from apps.cms.tests.admin.embed.test_embed_widget_admin import Member
from apps.event.models import CurrentProjectSchedule


class CMSEmbedWidgetAdminViewTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            password="testpass123",
            first_name="Embed",
            last_name="Admin",
        )
        ContactEmail.objects.create(
            member=self.admin_user,
            email_address="admin@example.com",
            email_type="primary",
            verified=True,
        )
        self.client.login(username="admin@example.com", password="testpass123")
        self.page = CMSPage.objects.create(slug="host", route="/host", title="Host", status="draft")
        self.schedule = CurrentProjectSchedule.objects.create(name="Demo Day")
        for i in range(2):
            CMSBlock.objects.create(
                page=self.page,
                block_type="rich_text",
                sort_order=i,
                admin_label=f"Block {i}",
                data={},
            )

    def test_changelist_renders(self):
        response = self.client.get(reverse("admin:cms_cmsembedwidget_changelist"))
        self.assertEqual(response.status_code, 200)

    def test_add_form_renders(self):
        response = self.client.get(reverse("admin:cms_cmsembedwidget_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Embed URL")
        self.assertContains(response, 'id="cms-widget-app-route-status"')
        self.assertContains(response, "Sections to hide")
        self.assertContains(response, "schedule_projects")
        self.assertContains(response, 'id="id_schedule"')
        self.assertContains(response, "cms/js/embed-widget/previews.js")

    def test_add_form_replaces_legacy_hide_toggle_with_hidden_section_presets(self):
        response = self.client.get(reverse("admin:cms_cmsembedwidget_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="hidden_sections"')
        self.assertContains(response, 'value="section_titles"')
        self.assertContains(response, 'value="schedule_projects"')
        self.assertContains(response, "hiddenSectionPresets")
        self.assertNotContains(response, 'name="hide_section_titles"')

    def test_page_blocks_endpoint_returns_blocks(self):
        url = reverse("admin:cms_cmsembedwidget_page_blocks")
        response = self.client.get(url, {"page_id": str(self.page.pk)})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["blocks"]), 2)
        self.assertEqual(payload["blocks"][0]["sort_order"], 0)
        self.assertEqual(payload["blocks"][0]["block_type"], "rich_text")
        self.assertEqual(payload["blocks"][0]["admin_label"], "Block 0")

    def test_page_blocks_endpoint_empty_without_page_id(self):
        url = reverse("admin:cms_cmsembedwidget_page_blocks")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"blocks": []})

    def test_page_blocks_endpoint_requires_staff(self):
        self.client.logout()
        url = reverse("admin:cms_cmsembedwidget_page_blocks")
        response = self.client.get(url, {"page_id": str(self.page.pk)})
        # Admin view redirects to login for anonymous users.
        self.assertIn(response.status_code, (302, 403))

    def test_app_routes_endpoint_returns_routes(self):
        url = reverse("admin:cms_cmsembedwidget_app_routes")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        urls = [r["url"] for r in payload["routes"]]
        self.assertIn("/schedule", urls)
        self.assertIn("/presenting-teams", urls)

    def test_app_routes_endpoint_requires_staff(self):
        self.client.logout()
        url = reverse("admin:cms_cmsembedwidget_app_routes")
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403))

    def test_page_info_endpoint_returns_title_and_route(self):
        url = reverse("admin:cms_cmsembedwidget_page_info")
        response = self.client.get(url, {"page_id": str(self.page.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"title": "Host", "route": "/host"})

    def test_page_info_endpoint_empty_without_page_id(self):
        url = reverse("admin:cms_cmsembedwidget_page_info")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"title": "", "route": ""})

    def test_page_info_endpoint_empty_for_unknown_page(self):
        import uuid

        url = reverse("admin:cms_cmsembedwidget_page_info")
        response = self.client.get(url, {"page_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"title": "", "route": ""})

    def test_change_view_renders_existing_widget(self):
        widget = CMSEmbedWidget.objects.create(page=self.page, slug="existing-widget", block_sort_orders=[0, 1])
        response = self.client.get(reverse("admin:cms_cmsembedwidget_change", args=[widget.pk]))
        self.assertEqual(response.status_code, 200)
        # _extra_context seeds the initial slug into the rendered change form.
        self.assertContains(response, "existing-widget")
