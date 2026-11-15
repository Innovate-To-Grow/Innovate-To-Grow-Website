"""Direct unit tests for ConfirmOnSaveMixin internal branches.

These exercise code paths that are awkward to hit through the full admin HTTP
flow: the popup skip, file-upload caching + restore, and the many short-circuit
branches inside ``response_action`` / ``_execute_confirmed_action``.
"""

from unittest.mock import MagicMock, patch

from django.contrib import admin
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.contrib.admin.options import IS_POPUP_VAR, TO_FIELD_VAR
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.test import RequestFactory, TestCase, override_settings

from apps.cms.models import CMSAsset, CMSEmbedAllowedHost
from apps.projects.models import Semester

User = get_user_model()


def _wire_request(request):
    request.session = SessionStore()
    request._messages = FallbackStorage(request)
    request.user = MagicMock(is_superuser=True, is_active=True, is_staff=True)
    return request


def _host_admin():
    return admin.site._registry[CMSEmbedAllowedHost]


def _semester_admin():
    return admin.site._registry[Semester]


def _asset_admin():
    return admin.site._registry[CMSAsset]


class ShouldSkipConfirmationTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = _host_admin()

    def test_skip_when_require_confirmation_false(self):
        request = _wire_request(self.factory.post("/admin/"))
        with patch.object(type(self.admin), "require_confirmation", False):
            self.assertTrue(self.admin._should_skip_confirmation(request))

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_skip_on_popup(self):
        request = _wire_request(self.factory.post("/admin/", {IS_POPUP_VAR: "1"}))
        self.assertTrue(self.admin._should_skip_confirmation(request))

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_removed_autosave_marker_no_longer_skips(self):
        """The admin autosave client is gone, so its ``_autosave`` marker must not remain a
        confirmation bypass that any client able to add a form field could still use."""
        request = _wire_request(self.factory.post("/admin/", {"_autosave": "1"}))
        self.assertFalse(self.admin._should_skip_confirmation(request))

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_no_skip_for_plain_post(self):
        request = _wire_request(self.factory.post("/admin/", {"x": "1"}))
        self.assertFalse(self.admin._should_skip_confirmation(request))


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ChangeformObjectMissingTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = _host_admin()

    def test_confirmed_save_marker_in_the_post_body_cannot_bypass_confirmation(self):
        """``_confirmed_save`` used to route straight to the real save, skipping the diff, the typed
        word and the session token — reachable by anyone able to add a form field."""
        request = _wire_request(self.factory.post("/admin/", {"_confirmed_save": "1", "hostname": "z.com"}))

        with patch("django.contrib.admin.options.ModelAdmin.changeform_view") as super_view:
            response = self.admin.changeform_view(request, object_id=None)

        super_view.assert_not_called()
        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertIn("confirm-change", response.url)

    def test_save_as_new_checks_add_permission_before_constructing_formsets(self):
        request = _wire_request(
            self.factory.post(
                "/admin/",
                {"_saveasnew": "1", "hostname": "copy.com", "is_active": "on"},
            )
        )

        with (
            patch.object(self.admin, "has_add_permission", return_value=False) as has_add,
            patch.object(self.admin, "get_object") as get_object,
            patch.object(self.admin, "_create_formsets") as create_formsets,
            patch.object(self.admin, "get_confirmation_diff") as diff_hook,
        ):
            with self.assertRaises(PermissionDenied):
                self.admin.changeform_view(request, object_id="existing-object")

        has_add.assert_called_once_with(request)
        get_object.assert_not_called()
        create_formsets.assert_not_called()
        diff_hook.assert_not_called()

    def test_change_checks_permission_before_constructing_formsets(self):
        host = CMSEmbedAllowedHost.objects.create(hostname="readonly.com", is_active=True)
        request = _wire_request(
            self.factory.post(
                "/admin/",
                {"hostname": "changed.com", "is_active": "on"},
            )
        )

        with (
            patch.object(self.admin, "has_change_permission", return_value=False) as has_change,
            patch.object(self.admin, "_create_formsets") as create_formsets,
            patch.object(self.admin, "get_confirmation_diff") as diff_hook,
        ):
            with self.assertRaises(PermissionDenied):
                self.admin.changeform_view(request, object_id=str(host.pk))

        has_change.assert_called_once_with(request, host)
        create_formsets.assert_not_called()
        diff_hook.assert_not_called()

    def test_disallowed_to_field_is_rejected_before_object_or_formset_lookup(self):
        request = _wire_request(
            self.factory.post(
                "/admin/",
                {
                    TO_FIELD_VAR: "hostname",
                    "hostname": "changed.com",
                    "is_active": "on",
                },
            )
        )

        with (
            patch.object(self.admin, "to_field_allowed", return_value=False) as allowed,
            patch.object(self.admin, "get_object") as get_object,
            patch.object(self.admin, "_create_formsets") as create_formsets,
            patch.object(self.admin, "get_confirmation_diff") as diff_hook,
        ):
            with self.assertRaises(DisallowedModelAdminToField):
                self.admin.changeform_view(request, object_id="existing-object")

        allowed.assert_called_once_with(request, "hostname")
        get_object.assert_not_called()
        create_formsets.assert_not_called()
        diff_hook.assert_not_called()

    def test_missing_object_defers_to_super(self):
        request = _wire_request(self.factory.post("/admin/", {"hostname": "x.com"}))
        sentinel = object()
        with (
            patch.object(self.admin, "get_object", return_value=None),
            patch(
                "django.contrib.admin.options.ModelAdmin.changeform_view",
                return_value=sentinel,
            ) as super_view,
        ):
            result = self.admin.changeform_view(request, object_id="deadbeef")
        self.assertIs(result, sentinel)
        super_view.assert_called_once()
