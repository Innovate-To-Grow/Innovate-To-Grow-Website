"""Per-Django-app admin access gating for the projects app.

These exercise the shared predicate (apps.core.access.user_can_access_app) through
the real Django admin via the test client: a staff member granted the ``projects``
app may reach the projects changelists but not another app's, a superuser reaches
everything, and a grant-less staff member is locked out.
"""

from django.test import TestCase

from apps.event.tests.helpers import make_admin, make_member, make_superuser

PROJECTS_CHANGELIST = "/admin/projects/project/"
SEMESTER_CHANGELIST = "/admin/projects/semester/"
CMS_CHANGELIST = "/admin/cms/cmspage/"


class ProjectsAdminPerAppAccessTest(TestCase):
    def test_projects_granted_staff_reaches_projects_changelist(self):
        make_admin(apps=["projects"], email="projadmin@example.com")
        self.client.login(username="projadmin@example.com", password="testpass123")

        self.assertEqual(self.client.get(PROJECTS_CHANGELIST).status_code, 200)
        self.assertEqual(self.client.get(SEMESTER_CHANGELIST).status_code, 200)

    def test_projects_granted_staff_denied_other_app_changelist(self):
        make_admin(apps=["projects"], email="projadmin@example.com")
        self.client.login(username="projadmin@example.com", password="testpass123")

        self.assertEqual(self.client.get(CMS_CHANGELIST).status_code, 403)

    def test_superuser_reaches_projects_and_other_app(self):
        make_superuser(email="master@example.com")
        self.client.login(username="master@example.com", password="testpass123")

        self.assertEqual(self.client.get(PROJECTS_CHANGELIST).status_code, 200)
        self.assertEqual(self.client.get(CMS_CHANGELIST).status_code, 200)

    def test_grantless_staff_denied_projects_changelist(self):
        # Staff member with no admin_apps grant — must not reach projects admin.
        make_admin(apps=[], email="nogrant@example.com")
        self.client.login(username="nogrant@example.com", password="testpass123")

        self.assertEqual(self.client.get(PROJECTS_CHANGELIST).status_code, 403)

    def test_non_staff_member_denied_projects_changelist(self):
        # A plain (non-staff) member is bounced to the admin login, never 200.
        make_member(email="plain@example.com")
        self.client.login(username="plain@example.com", password="testpass123")

        self.assertNotEqual(self.client.get(PROJECTS_CHANGELIST).status_code, 200)
