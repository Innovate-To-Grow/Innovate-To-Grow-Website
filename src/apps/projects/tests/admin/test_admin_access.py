"""Who may use the projects admin: every Admin reaches its changelists; a regular member is sent to the login page."""

from django.contrib import admin
from django.test import RequestFactory, TestCase

from apps.event.tests.helpers import make_admin, make_member
from apps.projects.models import Semester

PROJECTS_CHANGELIST = "/admin/projects/project/"
SEMESTER_CHANGELIST = "/admin/projects/semester/"
CMS_CHANGELIST = "/admin/cms/cmspage/"


class ProjectsAdminAccessTest(TestCase):
    def test_an_admin_reaches_the_projects_changelists_and_every_other_app(self):
        make_admin(email="projadmin@example.com")
        self.client.login(username="projadmin@example.com", password="testpass123")

        self.assertEqual(self.client.get(PROJECTS_CHANGELIST).status_code, 200)
        self.assertEqual(self.client.get(SEMESTER_CHANGELIST).status_code, 200)
        self.assertEqual(self.client.get(CMS_CHANGELIST).status_code, 200)

    def test_a_regular_member_is_sent_to_the_admin_login(self):
        make_member(email="plain@example.com")
        self.client.login(username="plain@example.com", password="testpass123")

        response = self.client.get(PROJECTS_CHANGELIST)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])


class ProjectInlineAccessTest(TestCase):
    """The Semester page's project inline follows the Admin rule (``AppAccessInlineMixin``), not Django codenames."""

    def _inline(self):
        semester_admin = admin.site._registry[Semester]
        return semester_admin.get_inline_instances(self._request(make_admin(email="inline-admin@example.com")))[0]

    @staticmethod
    def _request(user):
        request = RequestFactory().get("/")
        request.user = user
        return request

    def test_every_admin_may_view_add_change_and_delete_projects_inline(self):
        inline = self._inline()
        request = self._request(make_admin(email="other-admin@example.com"))

        self.assertTrue(inline.has_view_permission(request))
        self.assertTrue(inline.has_add_permission(request, None))
        self.assertTrue(inline.has_change_permission(request))
        self.assertTrue(inline.has_delete_permission(request))

    def test_a_regular_member_gets_nothing(self):
        inline = self._inline()
        request = self._request(make_member(email="inline-member@example.com"))

        self.assertFalse(inline.has_view_permission(request))
        self.assertFalse(inline.has_add_permission(request, None))
        self.assertFalse(inline.has_change_permission(request))
        self.assertFalse(inline.has_delete_permission(request))
