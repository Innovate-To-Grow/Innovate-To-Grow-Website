from unittest.mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.cms.admin.cms.cms_page import CMSPageAdmin, CMSPageAdminForm
from apps.cms.models import CMSPage, RouteRedirect
from apps.cms.tests.admin.routes.test_route_redirect_admin import Member


class RouteRedirectAdminEndpointTests(TestCase):
    def setUp(self):
        self.user = Member.objects.create_superuser(password="testpass123", first_name="Endpoint", last_name="Admin")
        self.client.force_login(self.user)
        self.target = CMSPage.objects.create(
            slug="endpoint-target",
            route="/endpoint-target",
            title="Endpoint Target",
            status="published",
        )

    def test_add_and_change_forms_render_admin_workflow(self):
        add_response = self.client.get(reverse("admin:cms_routeredirect_add"))
        self.assertEqual(add_response.status_code, 200)
        self.assertContains(add_response, "New mappings are saved inactive")
        self.assertContains(add_response, "permanent 301s")
        self.assertContains(add_response, "route-redirect-admin.js")

        redirect = RouteRedirect.objects.create(
            source_path="/legacy-render",
            destination_path=self.target.route,
        )
        change_response = self.client.get(reverse("admin:cms_routeredirect_change", args=[redirect.pk]))
        self.assertEqual(change_response.status_code, 200)
        self.assertContains(change_response, "/legacy-render")

    def test_live_conflict_endpoint_reports_application_collision(self):
        response = self.client.get(
            reverse("admin:cms_routeredirect_conflict_check"),
            {"source_path": "/schedule", "destination_path": "/endpoint-target"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["has_conflict"])
        self.assertIn("application_route", {item["code"] for item in response.json()["conflicts"]})

    def test_conflict_endpoint_requires_cms_app_access(self):
        other_staff = Member.objects.create_user(
            password="testpass123",
            is_staff=True,
            first_name="Other",
            last_name="Staff",
            admin_apps=[],
        )
        self.client.force_login(other_staff)

        response = self.client.get(
            reverse("admin:cms_routeredirect_conflict_check"),
            {"source_path": "/legacy", "destination_path": "/endpoint-target"},
        )

        self.assertEqual(response.status_code, 403)


class CMSPageRenameAdminTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.model_admin = CMSPageAdmin(CMSPage, self.site)
        self.request = RequestFactory().post("/admin/cms/cmspage/change/")
        self.request.user = Member.objects.create_superuser(
            password="testpass123",
            first_name="Rename",
            last_name="Admin",
        )
        self.page = CMSPage.objects.create(
            slug="renamed-page",
            route="/old-page-route",
            title="Renamed Page",
            status="published",
        )

    def test_published_page_form_defaults_keep_redirect_on(self):
        form = CMSPageAdminForm(instance=self.page)
        self.assertTrue(form.fields["keep_previous_url_as_redirect"].initial)

    def test_active_redirect_destination_cannot_be_deleted_in_admin(self):
        RouteRedirect.objects.create(
            source_path="/old-protected-page",
            destination_path=self.page.route,
            is_active=True,
        )

        self.assertFalse(self.model_admin.has_delete_permission(self.request, self.page))
        _deleted, _counts, _permissions, protected = self.model_admin.get_deleted_objects(
            CMSPage.objects.filter(pk=self.page.pk),
            self.request,
        )
        self.assertTrue(any("old-protected-page" in str(item) for item in protected))

    def test_rename_creates_old_mapping_and_retargets_existing_inbound_mapping(self):
        inbound = RouteRedirect.objects.create(
            source_path="/even-older-page",
            destination_path=self.page.route,
            is_active=True,
        )
        self.page.route = "/new-page-route"
        form = Mock(cleaned_data={"keep_previous_url_as_redirect": True})

        self.model_admin.save_model(self.request, self.page, form, change=True)

        inbound.refresh_from_db()
        self.assertEqual(inbound.destination_path, "/new-page-route")
        created = RouteRedirect.objects.get(source_path="/old-page-route")
        self.assertEqual(created.destination_path, "/new-page-route")
        self.assertTrue(created.is_active)

    def test_rename_without_keep_redirect_only_retargets_inbound_mapping(self):
        inbound = RouteRedirect.objects.create(
            source_path="/incoming",
            destination_path=self.page.route,
            is_active=True,
        )
        self.page.route = "/new-without-alias"
        form = Mock(cleaned_data={"keep_previous_url_as_redirect": False})

        self.model_admin.save_model(self.request, self.page, form, change=True)

        inbound.refresh_from_db()
        self.assertEqual(inbound.destination_path, "/new-without-alias")
        self.assertFalse(RouteRedirect.objects.filter(source_path="/old-page-route").exists())

    def test_rename_retargets_inactive_inbound_mapping_with_stale_source(self):
        inbound = RouteRedirect.objects.create(
            source_path="/legacy-now-owned-by-react",
            destination_path=self.page.route,
            is_active=False,
        )
        self.page.route = "/renamed-around-stale-inbound"
        form = Mock(cleaned_data={"keep_previous_url_as_redirect": False})

        with patch(
            "apps.cms.services.routing.route_redirects.PUBLIC_APP_ROUTES",
            [{"url": "/legacy-now-owned-by-react", "title": "New App Route"}],
        ):
            self.model_admin.save_model(self.request, self.page, form, change=True)

        inbound.refresh_from_db()
        self.assertEqual(inbound.destination_path, "/renamed-around-stale-inbound")
        self.assertFalse(inbound.is_active)
