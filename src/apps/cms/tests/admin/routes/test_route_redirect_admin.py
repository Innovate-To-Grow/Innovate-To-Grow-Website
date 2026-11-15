"""Route redirect and page-rename admin tests."""

from unittest.mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget, UnfoldAdminTextInputWidget

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

    @patch("apps.cms.services.amplify.jobs.schedule_amplify_redirect_sync")
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

    @patch("apps.cms.services.amplify.jobs.schedule_amplify_redirect_sync")
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
