from apps.cli_admin.tests.helpers import (
    CliApiTestCase,
    issue_token,
    make_admin,
    make_staff,
    make_superuser,
)
from apps.projects.models import Semester

COLLECTION = "/admin-api/records/projects/semester/"


def detail(pk):
    return f"/admin-api/records/projects/semester/{pk}/"


class AppAccessDeniedTests(CliApiTestCase):
    """A staff member WITHOUT the target app gets 403 on every record op."""

    def setUp(self):
        super().setUp()
        # Granted a different app only — no access to projects.
        self.staff = make_admin(apps=["cms"], email="noproj@example.com")
        _, self.raw = issue_token(self.staff)
        self.sem = Semester.objects.create(year=2060, season=1)

    def test_list_is_403(self):
        response = self.client.get(COLLECTION, **self.auth(self.raw))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"], "forbidden")
        self.assertIn("projects", response.data["detail"])

    def test_get_is_403(self):
        response = self.client.get(detail(self.sem.pk), **self.auth(self.raw))
        self.assertEqual(response.status_code, 403)

    def test_create_is_403(self):
        response = self.client.post(COLLECTION, {"year": 2061, "season": 1}, format="json", **self.auth(self.raw))
        self.assertEqual(response.status_code, 403)
        # No row was created.
        self.assertFalse(Semester.objects.filter(year=2061).exists())

    def test_update_is_403(self):
        response = self.client.patch(detail(self.sem.pk), {"is_published": True}, format="json", **self.auth(self.raw))
        self.assertEqual(response.status_code, 403)
        self.sem.refresh_from_db()
        self.assertFalse(self.sem.is_published)

    def test_delete_is_403(self):
        response = self.client.delete(detail(self.sem.pk), **self.auth(self.raw))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Semester.objects.filter(pk=self.sem.pk).exists())


class AppAccessGrantedTests(CliApiTestCase):
    """A staff member WITH the target app succeeds on every record op."""

    def setUp(self):
        super().setUp()
        self.staff = make_admin(apps=["projects"], email="hasproj@example.com")
        _, self.raw = issue_token(self.staff)
        self.sem = Semester.objects.create(year=2070, season=1)

    def test_list_succeeds(self):
        response = self.client.get(COLLECTION, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_get_succeeds(self):
        response = self.client.get(detail(self.sem.pk), **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["year"], 2070)

    def test_create_succeeds(self):
        response = self.client.post(COLLECTION, {"year": 2071, "season": 1}, format="json", **self.auth(self.raw))
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Semester.objects.filter(year=2071).exists())

    def test_update_succeeds(self):
        response = self.client.patch(detail(self.sem.pk), {"is_published": True}, format="json", **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_published"])

    def test_delete_succeeds(self):
        response = self.client.delete(detail(self.sem.pk), **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Semester.objects.filter(pk=self.sem.pk).exists())


class SuperuserAppAccessTests(CliApiTestCase):
    """A superuser (I2G Master) bypasses per-app access on every record op."""

    def setUp(self):
        super().setUp()
        self.super = make_superuser(email="master@example.com")
        _, self.raw = issue_token(self.super)
        self.sem = Semester.objects.create(year=2080, season=1)

    def test_list_succeeds(self):
        response = self.client.get(COLLECTION, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)

    def test_get_succeeds(self):
        response = self.client.get(detail(self.sem.pk), **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)

    def test_create_succeeds(self):
        response = self.client.post(COLLECTION, {"year": 2081, "season": 1}, format="json", **self.auth(self.raw))
        self.assertEqual(response.status_code, 201)

    def test_update_succeeds(self):
        response = self.client.patch(detail(self.sem.pk), {"is_published": True}, format="json", **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)

    def test_delete_succeeds(self):
        response = self.client.delete(detail(self.sem.pk), **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)


class WhoAmIAdminAppsTests(CliApiTestCase):
    def test_whoami_returns_admin_apps(self):
        staff = make_admin(apps=["projects", "cms"], email="whoapps@example.com")
        _, raw = issue_token(staff)
        response = self.client.get("/admin-api/whoami/", **self.auth(raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(response.data["admin_apps"]), ["cms", "projects"])

    def test_whoami_empty_admin_apps_for_ungranted_staff(self):
        staff = make_staff(email="noapps@example.com", apps=[])
        _, raw = issue_token(staff)
        response = self.client.get("/admin-api/whoami/", **self.auth(raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["admin_apps"], [])

    def test_whoami_superuser_admin_apps(self):
        # A superuser's admin_apps may be empty (the list is ignored for them).
        sup = make_superuser(email="superwho@example.com")
        _, raw = issue_token(sup)
        response = self.client.get("/admin-api/whoami/", **self.auth(raw))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_superuser"])
        self.assertIn("admin_apps", response.data)
