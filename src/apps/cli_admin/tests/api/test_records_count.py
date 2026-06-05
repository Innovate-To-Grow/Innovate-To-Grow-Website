from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff
from apps.projects.models import Semester

COLLECTION = "/admin-api/records/projects/semester/"


class RecordCountTests(CliApiTestCase):
    def setUp(self):
        super().setUp()
        self.staff = make_staff(email="reccount@example.com")
        _, self.raw = issue_token(self.staff)

    def _seed(self, count):
        return [Semester.objects.create(year=2050 + i, season=1) for i in range(count)]

    def test_count_returns_count_only(self):
        self._seed(3)
        response = self.client.get(COLLECTION, {"count": "1"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["model"], "projects.Semester")
        self.assertNotIn("results", response.data)
        self.assertNotIn("offset", response.data)
        self.assertNotIn("limit", response.data)

    def test_count_with_filter(self):
        self._seed(3)
        response = self.client.get(COLLECTION, {"count": "true", "filter": "year=2051"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn("results", response.data)

    def test_count_falsey_param_returns_full_list(self):
        self._seed(2)
        response = self.client.get(COLLECTION, {"count": "0"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 2)

    def test_count_bad_filter_key_is_400(self):
        response = self.client.get(COLLECTION, {"count": "1", "filter": "bogus=1"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)
