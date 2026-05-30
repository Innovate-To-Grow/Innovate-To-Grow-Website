import json
from unittest.mock import patch

from django.db import IntegrityError

from apps.cli_admin.models import CliAuditLog
from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff
from apps.core.services.db_tools.safe_orm import serialize_model_instance
from apps.projects.models import Project, Semester

COLLECTION = "/admin-api/records/projects/semester/"


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


class RecordWriteTests(CliApiTestCase):
    def setUp(self):
        super().setUp()
        self.staff = make_staff(email="recwrite@example.com")
        _, self.raw = issue_token(self.staff)

    def test_create_success_records_audit_and_ip(self):
        response = self.client.post(
            COLLECTION,
            {"year": 2040, "season": 1},
            format="json",
            HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1",
            **self.auth(self.raw),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["year"], 2040)
        log = CliAuditLog.objects.get(action="create", status="success")
        self.assertEqual(log.request_ip, "203.0.113.7")

    def test_create_validation_error_is_400_and_audits_failure(self):
        response = self.client.post(COLLECTION, {"year": 2041}, format="json", **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(CliAuditLog.objects.filter(action="create", status="failed").exists())

    def test_create_non_dict_body_is_400(self):
        response = self.client.post(COLLECTION, [1, 2], format="json", **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(CliAuditLog.objects.filter(action="create", status="failed").exists())

    def test_create_integrity_error_is_409(self):
        with patch("apps.cli_admin.views.records.cli_create", side_effect=IntegrityError("dup")):
            response = self.client.post(COLLECTION, {"year": 2042, "season": 1}, format="json", **self.auth(self.raw))
        self.assertEqual(response.status_code, 409)

    def test_malformed_json_body_is_400(self):
        response = self.client.post(
            COLLECTION, data="{bad json", content_type="application/json", **self.auth(self.raw)
        )
        self.assertEqual(response.status_code, 400)

    def test_update_success(self):
        sem = Semester.objects.create(year=2043, season=1)
        response = self.client.patch(detail(sem.pk), {"is_published": True}, format="json", **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_published"])
        self.assertTrue(CliAuditLog.objects.filter(action="update", status="success").exists())

    def test_update_matching_snapshot_succeeds(self):
        sem = Semester.objects.create(year=2044, season=1)
        snapshot = serialize_model_instance(sem, write=True)
        response = self.client.patch(
            detail(sem.pk),
            {"is_published": True},
            format="json",
            HTTP_X_EXPECTED_SNAPSHOT=json.dumps(snapshot),
            **self.auth(self.raw),
        )
        self.assertEqual(response.status_code, 200)

    def test_update_stale_snapshot_is_409(self):
        sem = Semester.objects.create(year=2045, season=1)
        response = self.client.patch(
            detail(sem.pk),
            {"is_published": True},
            format="json",
            HTTP_X_EXPECTED_SNAPSHOT=json.dumps({"year": 1900}),
            **self.auth(self.raw),
        )
        self.assertEqual(response.status_code, 409)

    def test_update_bad_snapshot_json_is_400(self):
        sem = Semester.objects.create(year=2046, season=1)
        response = self.client.patch(
            detail(sem.pk),
            {"is_published": True},
            format="json",
            HTTP_X_EXPECTED_SNAPSHOT="not-json",
            **self.auth(self.raw),
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_zero_cascade(self):
        sem = Semester.objects.create(year=2047, season=1)
        response = self.client.delete(detail(sem.pk), **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["deleted"])
        self.assertEqual(response.data["cascade"]["total"], 0)
        self.assertFalse(Semester.objects.filter(pk=sem.pk).exists())

    def test_delete_cascade_without_confirm_is_400(self):
        sem = Semester.objects.create(year=2048, season=1)
        Project.objects.create(semester=sem, project_title="Child")
        response = self.client.delete(detail(sem.pk), **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Semester.objects.filter(pk=sem.pk).exists())

    def test_delete_cascade_with_confirm_succeeds(self):
        sem = Semester.objects.create(year=2049, season=1)
        Project.objects.create(semester=sem, project_title="Child")
        response = self.client.delete(f"{detail(sem.pk)}?confirm_cascade=true", **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["cascade"]["total"], 1)
        self.assertFalse(Semester.objects.filter(pk=sem.pk).exists())
