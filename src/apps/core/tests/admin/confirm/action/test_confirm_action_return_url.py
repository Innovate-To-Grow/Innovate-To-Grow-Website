"""The typed confirmation of a bulk action goes back to the list it was chosen on.

The pending action keeps the changelist URL with its query (filters, search, sort) as ``return_url``; Cancel links
there and the confirmed action redirects there. Only this model's changelist is ever a way back: any other URL (or
none, from a pending action stored before the way back was kept) falls back to the bare changelist.
"""

from django.contrib.admin import helpers
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from apps.core.tests.admin.confirm.action.test_confirm_action import (
    ACTION_SESSION_KEY,
    _confirm_action_data,
    _make_semester,
    _make_superuser,
)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmActionReturnUrlTest(TestCase):
    def setUp(self):
        _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.semester = _make_semester()
        self.changelist = reverse("admin:projects_semester_changelist")
        self.view = f"{self.changelist}?is_published__exact=0&season__exact=1"
        self.confirm_url = reverse("admin:projects_semester_confirm_action")

    def choose(self, url):
        data = {
            "action": "publish_selected",
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(self.semester.pk)],
        }
        return self.client.post(url, data)

    def keep_return_url(self, url):
        session = self.client.session
        session[ACTION_SESSION_KEY] = {**session[ACTION_SESSION_KEY], "return_url": url}
        session.save()

    def test_the_pending_action_keeps_the_list_it_was_chosen_on(self):
        response = self.choose(self.view)

        self.assertRedirects(response, self.confirm_url, fetch_redirect_response=False)
        self.assertEqual(self.client.session[ACTION_SESSION_KEY]["return_url"], self.view)

    def test_cancel_goes_back_to_that_list(self):
        self.choose(self.view)

        response = self.client.get(self.confirm_url)

        self.assertEqual(response.context["cancel_url"], self.view)
        self.assertContains(response, f'href="{escape(self.view)}"')

    def test_the_confirmed_action_goes_back_to_that_list(self):
        self.choose(self.view)

        response = self.client.post(self.confirm_url, _confirm_action_data(self.client, "semester"))

        self.assertRedirects(response, self.view, fetch_redirect_response=False)
        self.semester.refresh_from_db()
        self.assertTrue(self.semester.is_published)

    def test_a_list_without_a_query_is_the_bare_changelist(self):
        self.choose(self.changelist)

        self.assertEqual(self.client.get(self.confirm_url).context["cancel_url"], self.changelist)
        response = self.client.post(self.confirm_url, _confirm_action_data(self.client, "semester"))
        self.assertRedirects(response, self.changelist, fetch_redirect_response=False)

    def test_a_way_back_that_is_not_this_models_list_falls_back_to_the_bare_changelist(self):
        self.choose(self.view)
        elsewhere = (
            "https://evil.example/admin/projects/semester/",
            "//evil.example/admin/projects/semester/",
            "/admin/projects/project/?season__exact=1",
            f"{self.changelist}{self.semester.pk}/change/",
            f"{self.changelist.rstrip('/')}-other/",
            "",
            None,
        )
        for url in elsewhere:
            with self.subTest(url):
                self.keep_return_url(url)
                self.assertEqual(self.client.get(self.confirm_url).context["cancel_url"], self.changelist)

        response = self.client.post(self.confirm_url, _confirm_action_data(self.client, "semester"))

        self.assertRedirects(response, self.changelist, fetch_redirect_response=False)
        self.semester.refresh_from_db()
        self.assertTrue(self.semester.is_published)

    def test_a_pending_action_stored_without_a_way_back_returns_to_the_bare_changelist(self):
        self.choose(self.view)
        session = self.client.session
        session[ACTION_SESSION_KEY] = {k: v for k, v in session[ACTION_SESSION_KEY].items() if k != "return_url"}
        session.save()

        self.assertEqual(self.client.get(self.confirm_url).context["cancel_url"], self.changelist)
        response = self.client.post(self.confirm_url, _confirm_action_data(self.client, "semester"))
        self.assertRedirects(response, self.changelist, fetch_redirect_response=False)
