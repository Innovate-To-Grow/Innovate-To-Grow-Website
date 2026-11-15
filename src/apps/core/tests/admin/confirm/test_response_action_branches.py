from unittest.mock import patch

from django.contrib.admin import helpers
from django.http import HttpResponseRedirect, QueryDict
from django.test import RequestFactory, TestCase, override_settings

from apps.core.tests.admin.confirm.test_confirm_on_save_direct import _semester_admin, _wire_request
from apps.projects.models import Semester


class _ResponseActionBranchesCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = _semester_admin()

    def _request(self, data):
        qd = QueryDict(mutable=True)
        for key, value in data.items():
            if isinstance(value, list):
                qd.setlist(key, value)
            else:
                qd[key] = value
        request = self.factory.post("/admin/", data=qd)
        return _wire_request(request)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ResponseActionBranchesTest(_ResponseActionBranchesCase):
    """Cover the short-circuit branches inside response_action."""

    def test_confirmed_action_marker_in_the_post_body_cannot_bypass_confirmation(self):
        """``_confirmed_action`` used to route straight to the real action, skipping the typed
        word and the session token — reachable by anyone able to add a form field."""
        semester = Semester.objects.create(year=2025, season=1, is_published=False)
        request = self._request(
            {
                "_confirmed_action": "1",
                "action": ["publish_selected"],
                "index": "0",
                "select_across": "0",
                helpers.ACTION_CHECKBOX_NAME: [str(semester.pk)],
            }
        )

        with patch("django.contrib.admin.options.ModelAdmin.response_action") as super_action:
            response = self.admin.response_action(request, Semester.objects.all())

        super_action.assert_not_called()
        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertIn("confirm-action", response.url)
        semester.refresh_from_db()
        self.assertFalse(semester.is_published)

    def test_non_integer_index_defaults_and_defers(self):
        # Bad index -> action_index 0, but no "action" list -> IndexError -> super().
        request = self._request({"index": "notanint"})
        sentinel = object()
        with patch(
            "django.contrib.admin.options.ModelAdmin.response_action",
            return_value=sentinel,
        ) as super_action:
            result = self.admin.response_action(request, Semester.objects.all())
        self.assertIs(result, sentinel)
        super_action.assert_called_once()

    def test_invalid_action_form_defers(self):
        request = self._request(
            {
                "action": ["not_a_real_action"],
                "index": "0",
                helpers.ACTION_CHECKBOX_NAME: ["x"],
            }
        )
        sentinel = object()
        with patch(
            "django.contrib.admin.options.ModelAdmin.response_action",
            return_value=sentinel,
        ) as super_action:
            result = self.admin.response_action(request, Semester.objects.all())
        self.assertIs(result, sentinel)
        super_action.assert_called_once()

    def test_no_selection_no_select_across_defers(self):
        request = self._request(
            {
                "action": ["publish_selected"],
                "index": "0",
                "select_across": "0",
                helpers.ACTION_CHECKBOX_NAME: [],
            }
        )
        sentinel = object()
        with patch(
            "django.contrib.admin.options.ModelAdmin.response_action",
            return_value=sentinel,
        ) as super_action:
            result = self.admin.response_action(request, Semester.objects.all())
        self.assertIs(result, sentinel)
        super_action.assert_called_once()

    def test_no_matching_pks_defers(self):
        # A valid selection that filters to zero rows -> super() at the action_pks guard.
        request = self._request(
            {
                "action": ["publish_selected"],
                "index": "0",
                "select_across": "0",
                helpers.ACTION_CHECKBOX_NAME: ["00000000-0000-0000-0000-000000000000"],
            }
        )
        sentinel = object()
        with patch(
            "django.contrib.admin.options.ModelAdmin.response_action",
            return_value=sentinel,
        ) as super_action:
            result = self.admin.response_action(request, Semester.objects.none())
        self.assertIs(result, sentinel)
        super_action.assert_called_once()

    def test_action_removed_after_validation_defers(self):
        """If the action vanishes from get_actions after form validation, defer to super."""
        semester = Semester.objects.create(year=2025, season=1, is_published=False)
        request = self._request(
            {
                "action": ["publish_selected"],
                "index": "0",
                "select_across": "0",
                helpers.ACTION_CHECKBOX_NAME: [str(semester.pk)],
            }
        )
        sentinel = object()
        real_get_actions = self.admin.get_actions
        calls = {"n": 0}

        def shrinking_get_actions(req):
            calls["n"] += 1
            # First calls (form choices, skip check) keep the action; the membership
            # guard at line ~324 sees it gone.
            actions = dict(real_get_actions(req))
            if calls["n"] >= 3:
                actions.pop("publish_selected", None)
            return actions

        with (
            patch.object(self.admin, "get_actions", side_effect=shrinking_get_actions),
            patch(
                "django.contrib.admin.options.ModelAdmin.response_action",
                return_value=sentinel,
            ) as super_action,
        ):
            result = self.admin.response_action(request, Semester.objects.all())
        self.assertIs(result, sentinel)
        super_action.assert_called_once()

    def test_description_format_error_falls_back_to_plain(self):
        """A description with an unmappable %-placeholder uses the raw description."""
        semester = Semester.objects.create(year=2025, season=1, is_published=False)
        request = self._request(
            {
                "action": ["publish_selected"],
                "index": "0",
                "select_across": "0",
                helpers.ACTION_CHECKBOX_NAME: [str(semester.pk)],
            }
        )
        real_get_actions = self.admin.get_actions

        # Django's get_action_choices formats with the full model_format_dict
        # (which includes verbose_name); the mixin only supplies
        # verbose_name_plural, so this key raises a KeyError there and falls
        # back to the raw description string.
        bad_desc = "Publish %(verbose_name)s now"

        def bad_description(req):
            actions = dict(real_get_actions(req))
            func, name, _desc = actions["publish_selected"]
            actions["publish_selected"] = (func, name, bad_desc)
            return actions

        with patch.object(self.admin, "get_actions", side_effect=bad_description):
            response = self.admin.response_action(request, Semester.objects.all())
        self.assertIsInstance(response, HttpResponseRedirect)
        pending = request.session[self.admin._session_action_key()]
        # KeyError on the format -> stored description is the raw string.
        self.assertEqual(pending["action_description"], bad_desc)
