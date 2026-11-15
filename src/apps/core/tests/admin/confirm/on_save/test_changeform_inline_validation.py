from unittest.mock import MagicMock, patch

from django.http import HttpResponseRedirect
from django.test import RequestFactory, TestCase, override_settings

from apps.core.tests.admin.confirm.on_save.test_confirm_on_save_direct import _host_admin, _wire_request


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ChangeformInlineValidationTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = _host_admin()

    def test_confirmation_diff_hook_receives_validated_formsets(self):
        request = _wire_request(
            self.factory.post(
                "/admin/",
                {"hostname": "hook-arguments.com", "is_active": "on"},
            )
        )
        formset = MagicMock()
        formset.is_valid.return_value = True
        custom_diff = [{"field": "inline", "label": "Inline", "new_value": "Included"}]

        with (
            patch.object(self.admin, "_create_formsets", return_value=([formset], [object()])),
            patch.object(self.admin, "get_confirmation_diff", return_value=custom_diff) as diff_hook,
        ):
            response = self.admin.changeform_view(request, object_id=None)

        self.assertIsInstance(response, HttpResponseRedirect)
        formset.is_valid.assert_called_once_with()
        diff_hook.assert_called_once()
        hook_request, hook_obj, hook_form, hook_formsets, hook_action_type = diff_hook.call_args.args
        self.assertIs(hook_request, request)
        self.assertIsNone(hook_obj)
        self.assertTrue(hook_form.is_valid())
        self.assertEqual(hook_formsets, [formset])
        self.assertEqual(hook_action_type, "add")
        self.assertEqual(request.session[self.admin._session_key()]["diff"], custom_diff)

    def test_invalid_inline_formset_returns_normal_change_form_without_confirmation(self):
        request = _wire_request(
            self.factory.post(
                "/admin/",
                {"hostname": "invalid-inline.com", "is_active": "on"},
            )
        )
        invalid_formset = MagicMock()
        invalid_formset.is_valid.return_value = False
        normal_change_form = object()

        with (
            patch.object(self.admin, "_create_formsets", return_value=([invalid_formset], [object()])),
            patch.object(self.admin, "get_confirmation_diff") as diff_hook,
            patch(
                "django.contrib.admin.options.ModelAdmin.changeform_view",
                return_value=normal_change_form,
            ) as super_view,
        ):
            response = self.admin.changeform_view(request, object_id=None)

        self.assertIs(response, normal_change_form)
        invalid_formset.is_valid.assert_called_once_with()
        diff_hook.assert_not_called()
        super_view.assert_called_once()
        self.assertEqual(super_view.call_args.args[:3], (request, None, ""))
        self.assertNotIn(self.admin._session_key(), request.session)
