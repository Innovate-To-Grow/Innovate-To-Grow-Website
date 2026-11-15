from unittest.mock import patch

from django.http import HttpResponseRedirect
from django.test import RequestFactory, TestCase, override_settings

from apps.core.tests.admin.confirm.on_save.test_confirm_on_save_direct import _semester_admin, _wire_request
from apps.projects.models import Semester


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ExecuteConfirmedActionTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = _semester_admin()

    def test_action_no_longer_available(self):
        request = _wire_request(self.factory.post("/admin/"))
        pending = {
            "action_name": "vanished_action",
            "selected_pks": [],
            "select_across": False,
            "queryset_pks": [],
        }
        request.session[self.admin._session_action_key()] = pending
        response = self.admin._execute_confirmed_action(request, pending)
        self.assertIsInstance(response, HttpResponseRedirect)
        messages_list = [str(m) for m in request._messages]
        self.assertIn("Action no longer available.", messages_list)

    def test_falls_back_to_changelist_when_action_returns_none(self):
        semester = Semester.objects.create(year=2025, season=1, is_published=False)
        request = _wire_request(self.factory.post("/admin/"))
        pending = {
            "action_name": "publish_selected",
            "selected_pks": [str(semester.pk)],
            "select_across": False,
            "queryset_pks": [str(semester.pk)],
        }
        # publish_selected returns None -> redirect to changelist.
        response = self.admin._execute_confirmed_action(request, pending)
        self.assertIsInstance(response, HttpResponseRedirect)
        semester.refresh_from_db()
        self.assertTrue(semester.is_published)

    def test_queryset_pks_none_uses_selected(self):
        semester = Semester.objects.create(year=2025, season=1, is_published=False)
        request = _wire_request(self.factory.post("/admin/"))
        pending = {
            "action_name": "publish_selected",
            "selected_pks": [str(semester.pk)],
            "select_across": False,
            "queryset_pks": None,
        }
        self.admin._execute_confirmed_action(request, pending)
        semester.refresh_from_db()
        self.assertTrue(semester.is_published)

    def test_action_returning_http_response_is_passed_through(self):
        """When the action returns an HttpResponse, it is returned directly."""
        from django.http import HttpResponse

        semester = Semester.objects.create(year=2025, season=1, is_published=False)
        request = _wire_request(self.factory.post("/admin/"))
        pending = {
            "action_name": "publish_selected",
            "selected_pks": [str(semester.pk)],
            "select_across": False,
            "queryset_pks": [str(semester.pk)],
        }
        custom_response = HttpResponse("custom body")
        real_get_actions = self.admin.get_actions

        def with_response_action(req):
            actions = dict(real_get_actions(req))
            _func, name, desc = actions["publish_selected"]
            actions["publish_selected"] = (lambda admin, r, qs: custom_response, name, desc)
            return actions

        with patch.object(self.admin, "get_actions", side_effect=with_response_action):
            response = self.admin._execute_confirmed_action(request, pending)
        self.assertIs(response, custom_response)
