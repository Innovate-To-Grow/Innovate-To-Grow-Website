from apps.cli_admin.tests.helpers import (
    CliApiTestCase,
    issue_token,
    make_member,
    make_staff,
)
from apps.projects.models import Semester

COLLECTION = "/admin-api/records/projects/semester/"


def detail(pk):
    return f"/admin-api/records/projects/semester/{pk}/"


class AdminAppAccessTests(CliApiTestCase):
    """Every Admin succeeds on every record op of an app the CLI does not deny."""

    def setUp(self):
        super().setUp()
        self.staff = make_staff(email="hasproj@example.com")
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


class WhoAmICompatibilityTests(CliApiTestCase):
    """whoami keeps its keys for installed CLIs, except the retired admin_apps."""

    def test_admin_apps_is_gone(self):
        _, raw = issue_token(make_staff(email="whoapps@example.com"))
        response = self.client.get("/admin-api/whoami/", **self.auth(raw))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("admin_apps", response.data)
        self.assertEqual(
            set(response.data),
            {"member_uuid", "name", "email", "is_staff", "is_active", "is_superuser", "token_expires_at"},
        )

    def test_is_superuser_follows_is_staff_not_the_column(self):
        # Clients released since 2026-08-05 list every app only when is_superuser is true, so it is true for every
        # Admin, whatever the stored column says.
        staff = make_staff(email="compat@example.com")
        type(staff).objects.filter(pk=staff.pk).update(is_superuser=False)
        _, raw = issue_token(staff)
        response = self.client.get("/admin-api/whoami/", **self.auth(raw))
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.data["is_superuser"], True)
        self.assertIs(response.data["is_staff"], True)


class RegularMemberAccessTests(CliApiTestCase):
    """A regular member's token is refused before any app is resolved."""

    def test_record_ops_are_refused(self):
        _, raw = issue_token(make_member(email="regular@example.com"))
        for response in (
            self.client.get(COLLECTION, **self.auth(raw)),
            self.client.get("/admin-api/apps/", **self.auth(raw)),
            self.client.get("/admin-api/whoami/", **self.auth(raw)),
        ):
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertIn(response.status_code, (401, 403))
