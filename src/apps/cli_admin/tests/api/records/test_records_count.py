from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff
from apps.projects.models import Semester

COLLECTION = "/admin-api/records/projects/semester/"


def _count_aggregate_queries(captured):
    """How many executed statements are SELECT COUNT(*) aggregates."""
    return sum(1 for q in captured.captured_queries if "count(" in q["sql"].lower())


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

    def test_list_first_page_not_full_count_is_exact(self):
        # offset=0 and fewer rows than the limit -> count == len(rows), no extra query.
        self._seed(3)
        response = self.client.get(COLLECTION, {"limit": "10"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 3)

    def test_list_full_first_page_count_is_exact(self):
        # offset=0 and a full page -> there may be more rows, so the count must
        # still reflect the true total (here exactly the page size).
        self._seed(5)
        response = self.client.get(COLLECTION, {"limit": "5"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 5)
        self.assertEqual(len(response.data["results"]), 5)

    def test_list_full_page_with_more_rows_count_is_total(self):
        # A full page that does NOT exhaust the queryset must report the full total.
        self._seed(7)
        response = self.client.get(COLLECTION, {"limit": "5"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 7)
        self.assertEqual(len(response.data["results"]), 5)

    def test_list_with_offset_count_is_total(self):
        # offset>0 must always run the full COUNT(*) so pagination stays correct.
        self._seed(4)
        response = self.client.get(COLLECTION, {"limit": "10", "offset": "2"}, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 4)
        self.assertEqual(len(response.data["results"]), 2)

    def test_list_short_first_page_skips_count_query(self):
        # The optimization: an unfilled first page must not emit a SELECT COUNT(*).
        self._seed(2)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(COLLECTION, {"limit": "10"}, **self.auth(self.raw))
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(_count_aggregate_queries(captured), 0)

    def test_list_full_first_page_runs_count_query(self):
        # A full page may have more rows, so the COUNT(*) is still issued.
        self._seed(3)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(COLLECTION, {"limit": "3"}, **self.auth(self.raw))
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(_count_aggregate_queries(captured), 1)

    def test_list_with_offset_runs_count_query(self):
        # offset>0 always runs the COUNT(*) even on a short page.
        self._seed(4)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(COLLECTION, {"limit": "10", "offset": "1"}, **self.auth(self.raw))
        self.assertEqual(response.data["count"], 4)
        self.assertEqual(_count_aggregate_queries(captured), 1)
