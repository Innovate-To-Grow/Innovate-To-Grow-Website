from unittest.mock import patch

from django.contrib.admin import helpers
from django.test import override_settings

from apps.core.tests.admin.confirm.test_response_action_branches import _ResponseActionBranchesCase
from apps.projects.models import Semester


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ResponseActionBranchesTest(_ResponseActionBranchesCase):
    def test_action_with_no_confirmation_attr_skips(self):
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
        # Patch the action func to carry no_confirmation = True so it skips.
        actions = dict(self.admin.get_actions(request))
        func = actions["publish_selected"][0]
        with (
            patch.object(func, "no_confirmation", True, create=True),
            patch(
                "django.contrib.admin.options.ModelAdmin.response_action",
                return_value=sentinel,
            ) as super_action,
        ):
            result = self.admin.response_action(request, Semester.objects.all())
        self.assertIs(result, sentinel)
        super_action.assert_called_once()
