from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff
from apps.projects.models import Semester

COLLECTION = "/admin-api/records/projects/semester/"

# Behind the ALB (NUM_PROXIES=1) the rightmost X-Forwarded-For entry is the one the trusted proxy appended;
# anything to its left is caller-supplied and must never reach the audit row.
FORGED_XFF = "198.51.100.99, 203.0.113.7"
TRUSTED_IP = "203.0.113.7"


def detail(pk):
    return f"/admin-api/records/projects/semester/{pk}/"


class RecordReadTests(CliApiTestCase):
    def setUp(self):
        super().setUp()
        self.staff = make_staff(email="recread@example.com")
        _, self.raw = issue_token(self.staff)

    def _seed(self, count):
        return [Semester.objects.create(year=2030 + i, season=1) for i in range(count)]

    def test_list_default(self):
        self._seed(2)
        response = self.client.get(COLLECTION, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["model"], "projects.Semester")
        self.assertEqual(len(response.data["results"]), 2)

    def test_list_selected_fields_only(self):
        self._seed(1)
        response = self.client.get(COLLECTION, {"field": "year"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data["results"][0].keys()), {"year"})

    def test_list_with_filter(self):
        self._seed(3)
        response = self.client.get(COLLECTION, {"filter": "year=2031"}, **self.auth(self.raw))
        self.assertEqual(response.data["count"], 1)

    def test_list_bad_filter_format_is_400(self):
        response = self.client.get(COLLECTION, {"filter": "yearonly"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)

    def test_list_bad_filter_key_is_400(self):
        response = self.client.get(COLLECTION, {"filter": "bogus=1"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)

    def test_list_bad_filter_value_is_400(self):
        # Valid key + lookup, but a non-integer value for an integer field only
        # fails at query execution; it must map to 400, not a 500.
        response = self.client.get(COLLECTION, {"filter": "year__gt=abc"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)

    def test_list_with_ordering(self):
        self._seed(2)
        response = self.client.get(COLLECTION, {"order": "-year"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["year"], 2031)

    def test_list_bad_ordering_key_is_400(self):
        response = self.client.get(COLLECTION, {"order": "bogus"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)

    def test_list_limit_is_capped(self):
        response = self.client.get(COLLECTION, {"limit": "999"}, **self.auth(self.raw))
        self.assertEqual(response.data["limit"], 50)

    def test_list_nonpositive_limit_resets(self):
        response = self.client.get(COLLECTION, {"limit": "0"}, **self.auth(self.raw))
        self.assertEqual(response.data["limit"], 50)

    def test_list_bad_limit_is_400(self):
        response = self.client.get(COLLECTION, {"limit": "abc"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)

    def test_list_offset(self):
        self._seed(3)
        response = self.client.get(COLLECTION, {"offset": "1", "order": "year"}, **self.auth(self.raw))
        self.assertEqual(response.data["offset"], 1)
        self.assertEqual(response.data["results"][0]["year"], 2031)

    def test_get_detail(self):
        sem = self._seed(1)[0]
        response = self.client.get(detail(sem.pk), **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["year"], 2030)

    def test_get_detail_missing_is_404(self):
        response = self.client.get(detail("00000000-0000-0000-0000-000000000000"), **self.auth(self.raw))
        self.assertEqual(response.status_code, 404)

    def test_get_detail_bad_pk_is_400(self):
        response = self.client.get(detail("not-a-uuid"), **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)
