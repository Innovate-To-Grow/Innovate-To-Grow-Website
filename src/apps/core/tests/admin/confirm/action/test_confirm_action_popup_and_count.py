"""Typed confirmation of a bulk action: a posted ``_popup`` never skips it (Django offers no actions in a popup, so the
flag is no way around the typed word), and the page counts one item in the singular."""

from django.contrib.admin import helpers
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.tests.admin.confirm.action.test_confirm_action import (
    ACTION_SESSION_KEY,
    _make_semester,
    _make_superuser,
)
from apps.projects.models import Semester


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmActionPopupAndCountTest(TestCase):
    def setUp(self):
        _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.changelist = reverse("admin:projects_semester_changelist")
        self.confirm_url = reverse("admin:projects_semester_confirm_action")

    def choose(self, *semesters, **extra):
        data = {
            "action": "publish_selected",
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(semester.pk) for semester in semesters],
            **extra,
        }
        return self.client.post(self.changelist, data)

    def test_a_posted_popup_flag_does_not_skip_the_typed_word(self):
        semester = _make_semester()

        response = self.choose(semester, _popup="1")

        self.assertRedirects(response, self.confirm_url, fetch_redirect_response=False)
        self.assertIn(ACTION_SESSION_KEY, self.client.session)
        semester.refresh_from_db()
        self.assertFalse(semester.is_published)

    def test_the_page_counts_one_item_in_the_singular_and_more_in_the_plural(self):
        one, other = _make_semester(), _make_semester(year=2026)
        meta = Semester._meta

        self.choose(one)
        single = self.client.get(self.confirm_url)
        self.choose(one, other)
        plural = self.client.get(self.confirm_url)

        self.assertContains(single, f"<strong>1</strong> {meta.verbose_name}.", html=False)
        self.assertNotContains(single, f"1 {meta.verbose_name_plural}")
        self.assertContains(plural, f"<strong>2</strong> {meta.verbose_name_plural}.", html=False)
