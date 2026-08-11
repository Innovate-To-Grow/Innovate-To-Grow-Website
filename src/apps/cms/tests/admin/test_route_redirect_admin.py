"""Route redirect and page-rename admin tests."""

from unittest.mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget, UnfoldAdminTextInputWidget

from apps.cms.admin.cms.cms_page import CMSPageAdmin, CMSPageAdminForm
from apps.cms.admin.cms.route_redirect import RouteRedirectAdmin, RouteRedirectAdminForm
from apps.cms.models import CMSPage, RouteRedirect

Member = get_user_model()


class RouteRedirectAdminTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.model_admin = RouteRedirectAdmin(RouteRedirect, self.site)
        self.request = RequestFactory().get("/admin/cms/routeredirect/")
        self.user = Member.objects.create_superuser(password="testpass123", first_name="Route", last_name="Admin")
        self.request.user = self.user
        self.target = CMSPage.objects.create(
            slug="admin-target",
            route="/admin-target-page",
            title="Admin Target",
            status="published",
        )

    def test_destination_picker_contains_published_pages_and_app_routes(self):
        form = RouteRedirectAdminForm()
        choices = str(form.fields["destination_path"].choices)
        self.assertIn("/admin-target-page", choices)
        self.assertIn("/schedule", choices)
        self.assertIn("Homepage (/)", choices)

    def test_editable_fields_use_unfold_widgets(self):
        form = RouteRedirectAdminForm()
        expected_widgets = {
            "source_path": UnfoldAdminTextInputWidget,
            "destination_path": UnfoldAdminSelectWidget,
            "notes": UnfoldAdminTextareaWidget,
        }

        for field_name, widget_class in expected_widgets.items():
            widget = form.fields[field_name].widget
            with self.subTest(field=field_name):
                self.assertIsInstance(widget, widget_class)
                self.assertIn("border-base-200", widget.attrs["class"])
                self.assertIn("dark:bg-base-900", widget.attrs["class"])

    def test_source_is_readonly_after_creation_and_delete_is_disabled(self):
        redirect = RouteRedirect.objects.create(source_path="/legacy-admin", destination_path=self.target.route)
        self.assertIn("is_active", self.model_admin.get_readonly_fields(self.request))
        self.assertIn("source_path", self.model_admin.get_readonly_fields(self.request, redirect))
        self.assertNotIn("is_active", self.model_admin.get_readonly_fields(self.request, redirect))
        self.assertFalse(self.model_admin.has_delete_permission(self.request, redirect))
        self.assertNotIn("delete_selected", self.model_admin.get_actions(self.request))

    def test_activate_and_deactivate_actions(self):
        redirect = RouteRedirect.objects.create(source_path="/legacy-actions", destination_path=self.target.route)
        self.model_admin.message_user = Mock()

        self.model_admin.activate_redirects(self.request, RouteRedirect.objects.filter(pk=redirect.pk))
        redirect.refresh_from_db()
        self.assertTrue(redirect.is_active)

        self.model_admin.deactivate_redirects(self.request, RouteRedirect.objects.filter(pk=redirect.pk))
        redirect.refresh_from_db()
        self.assertFalse(redirect.is_active)

    def test_change_form_can_deactivate_a_mapping_that_now_conflicts(self):
        redirect = RouteRedirect.objects.create(
            source_path="/legacy-form-recovery",
            destination_path=self.target.route,
            is_active=True,
        )
        with patch(
            "apps.cms.services.routing.route_redirects.PUBLIC_APP_ROUTES",
            [{"url": "/legacy-form-recovery", "title": "New App Route"}],
        ):
            form = RouteRedirectAdminForm(
                instance=redirect,
                data={
                    "source_path": redirect.source_path,
                    "destination_path": redirect.destination_path,
                    "is_active": False,
                    "notes": redirect.notes,
                },
            )
            self.assertTrue(form.is_valid(), form.errors)

    @patch("apps.cms.services.amplify.amplify_redirects.schedule_amplify_redirect_sync")
    def test_retry_action_marks_pending_and_schedules_global_sync(self, schedule):
        schedule.return_value = object()
        redirect = RouteRedirect.objects.create(
            source_path="/legacy-retry",
            destination_path=self.target.route,
            is_active=True,
        )
        RouteRedirect.objects.filter(pk=redirect.pk).update(edge_sync_status="failed", edge_sync_error="boom")
        self.model_admin.message_user = Mock()

        self.model_admin.retry_edge_sync(self.request, RouteRedirect.objects.filter(pk=redirect.pk))

        redirect.refresh_from_db()
        self.assertEqual(redirect.edge_sync_status, "pending")
        self.assertEqual(redirect.edge_sync_error, "")
        schedule.assert_called_once_with(immediate=True, redirect_ids=[redirect.pk])

    @patch("apps.cms.services.amplify.amplify_redirects.schedule_amplify_redirect_sync")
    def test_retry_action_ignores_inactive_unmanaged_redirect(self, schedule):
        redirect = RouteRedirect.objects.create(
            source_path="/legacy-inactive-retry",
            destination_path=self.target.route,
            is_active=False,
        )
        RouteRedirect.objects.filter(pk=redirect.pk).update(
            edge_sync_status="failed",
            edge_sync_error="access denied",
            edge_sync_attempted_at=redirect.updated_at,
            edge_synced_at=redirect.updated_at,
            edge_rule_managed=False,
        )
        self.model_admin.message_user = Mock()

        self.model_admin.retry_edge_sync(self.request, RouteRedirect.objects.filter(pk=redirect.pk))

        redirect.refresh_from_db()
        self.assertEqual(redirect.edge_sync_status, "failed")
        self.assertEqual(redirect.edge_sync_error, "access denied")
        schedule.assert_not_called()


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
