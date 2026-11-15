from django.contrib.admin import helpers
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.tests.admin.confirm.test_confirm_action import _confirm_action_data, _make_semester, _make_superuser
from apps.projects.models import Semester


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmActionExemptTest(TestCase):
    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_export_action_bypasses_confirmation(self):
        semester = _make_semester()
        url = reverse("admin:projects_semester_changelist")
        data = {
            "action": "export_data",
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(semester.pk)],
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("confirm-action", response.get("Location", ""))


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class ConfirmActionDisabledTest(TestCase):
    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_action_executes_immediately_when_disabled(self):
        semester = _make_semester()
        url = reverse("admin:projects_semester_changelist")
        data = {
            "action": "publish_selected",
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(semester.pk)],
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("confirm-action", response.url)
        semester.refresh_from_db()
        self.assertTrue(semester.is_published)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmActionDeleteSelectedTest(TestCase):
    """Django's built-in delete_selected should also require typed confirmation."""

    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_delete_selected_redirects_to_confirmation(self):
        semester = _make_semester()
        url = reverse("admin:projects_semester_changelist")
        data = {
            "action": "delete_selected",
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(semester.pk)],
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        self.assertIn("confirm-action", response.url)

    def test_delete_selected_shows_resolved_model_name(self):
        semester = _make_semester()
        url = reverse("admin:projects_semester_changelist")
        data = {
            "action": "delete_selected",
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(semester.pk)],
        }
        self.client.post(url, data)

        confirm_url = reverse("admin:projects_semester_confirm_action")
        response = self.client.get(confirm_url)

        self.assertContains(response, "Delete selected semesters")
        self.assertNotContains(response, "%(verbose_name_plural)s")

    def test_delete_selected_executes_after_confirmation(self):
        semester = _make_semester()
        url = reverse("admin:projects_semester_changelist")
        data = {
            "action": "delete_selected",
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(semester.pk)],
        }
        self.client.post(url, data)

        confirm_url = reverse("admin:projects_semester_confirm_action")
        self.client.post(confirm_url, _confirm_action_data(self.client, "semester"))

        self.assertFalse(Semester.objects.filter(pk=semester.pk).exists())


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmActionSelectAcrossTest(TestCase):
    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_select_across_shows_total_count(self):
        _make_semester(year=2024, season=1)
        _make_semester(year=2023, season=1)
        _make_semester(year=2022, season=1)

        url = reverse("admin:projects_semester_changelist")
        data = {
            "action": "publish_selected",
            "index": "0",
            "select_across": "1",
            helpers.ACTION_CHECKBOX_NAME: [""],
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        self.assertIn("confirm-action", response.url)

        confirm_url = reverse("admin:projects_semester_confirm_action")
        response = self.client.get(confirm_url)
        self.assertContains(response, "3")

    def test_select_across_executes_on_all(self):
        s1 = _make_semester(year=2024, season=1)
        s2 = _make_semester(year=2023, season=1)

        url = reverse("admin:projects_semester_changelist")
        data = {
            "action": "publish_selected",
            "index": "0",
            "select_across": "1",
            helpers.ACTION_CHECKBOX_NAME: [""],
        }
        self.client.post(url, data)

        confirm_url = reverse("admin:projects_semester_confirm_action")
        self.client.post(confirm_url, _confirm_action_data(self.client, "semester"))

        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertTrue(s1.is_published)
        self.assertTrue(s2.is_published)

    def test_select_across_preserves_changelist_filter(self):
        included = _make_semester(year=2024, season=1)
        excluded = _make_semester(year=2023, season=1)

        url = f"{reverse('admin:projects_semester_changelist')}?year__exact=2024"
        data = {
            "action": "publish_selected",
            "index": "0",
            "select_across": "1",
            helpers.ACTION_CHECKBOX_NAME: [""],
        }
        self.client.post(url, data)

        confirm_url = reverse("admin:projects_semester_confirm_action")
        response = self.client.get(confirm_url)
        self.assertContains(response, "1")
        self.client.post(confirm_url, _confirm_action_data(self.client, "semester"))

        included.refresh_from_db()
        excluded.refresh_from_db()
        self.assertTrue(included.is_published)
        self.assertFalse(excluded.is_published)
