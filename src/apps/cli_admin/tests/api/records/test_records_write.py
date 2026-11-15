import json
from unittest.mock import patch

from django.db import IntegrityError
from django.test import override_settings

from apps.cli_admin.models import CliAuditLog
from apps.cli_admin.tests.api.records.test_records_crud import COLLECTION, FORGED_XFF, TRUSTED_IP, detail
from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff
from apps.core.services.db_tools.safe_orm import serialize_model_instance
from apps.projects.models import Project, Semester


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

    # records.py resolves the audit IP at four independent call sites (the create / update / delete service
    # calls and the ``_write`` failure handler), so each one gets its own forged-hop test.
    @override_settings(NUM_PROXIES=1)
    def test_create_audit_ip_ignores_forged_leftmost_forwarded_hop(self):
        response = self.client.post(
            COLLECTION,
            {"year": 2043, "season": 1},
            format="json",
            HTTP_X_FORWARDED_FOR=FORGED_XFF,
            **self.auth(self.raw),
        )
        self.assertEqual(response.status_code, 201)
        log = CliAuditLog.objects.get(action="create", status="success")
        self.assertEqual(log.request_ip, TRUSTED_IP)

    @override_settings(NUM_PROXIES=1)
    def test_failed_write_audit_ip_ignores_forged_leftmost_forwarded_hop(self):
        # The failed-audit row is written by ``_write``'s own handler, not by the service layer.
        response = self.client.post(
            COLLECTION, {"year": 2041}, format="json", HTTP_X_FORWARDED_FOR=FORGED_XFF, **self.auth(self.raw)
        )
        self.assertEqual(response.status_code, 400)
        log = CliAuditLog.objects.get(action="create", status="failed")
        self.assertEqual(log.request_ip, TRUSTED_IP)

    @override_settings(NUM_PROXIES=1)
    def test_update_audit_ip_ignores_forged_leftmost_forwarded_hop(self):
        sem = Semester.objects.create(year=2050, season=1)
        response = self.client.patch(
            detail(sem.pk),
            {"is_published": True},
            format="json",
            HTTP_X_FORWARDED_FOR=FORGED_XFF,
            **self.auth(self.raw),
        )
        self.assertEqual(response.status_code, 200)
        log = CliAuditLog.objects.get(action="update", status="success")
        self.assertEqual(log.request_ip, TRUSTED_IP)

    @override_settings(NUM_PROXIES=1)
    def test_delete_audit_ip_ignores_forged_leftmost_forwarded_hop(self):
        sem = Semester.objects.create(year=2051, season=1)
        response = self.client.delete(detail(sem.pk), HTTP_X_FORWARDED_FOR=FORGED_XFF, **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        log = CliAuditLog.objects.get(action="delete", status="success")
        self.assertEqual(log.request_ip, TRUSTED_IP)

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
