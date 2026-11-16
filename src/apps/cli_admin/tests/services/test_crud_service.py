from django.test import TestCase

from apps.cli_admin.models import CliAuditLog
from apps.cli_admin.services.crud import (
    CascadeNotConfirmedError,
    StaleSnapshotError,
    cli_create,
    cli_delete,
    cli_update,
)
from apps.cli_admin.services.resolve import CliAppAccessDenied
from apps.core.services.db_tools.safe_orm import ActionRequestError, serialize_model_instance
from apps.event.tests.helpers import make_admin
from apps.projects.models import Project, Semester


class CrudServiceTests(TestCase):
    def setUp(self):
        self.actor = make_admin(apps=["projects"], email="crud@example.com")

    # ---- create ---------------------------------------------------------
    def test_create_success_writes_audit(self):
        obj = cli_create(
            actor=self.actor,
            request_ip="10.0.0.1",
            app_label="projects",
            model_name="semester",
            fields={"year": 2031, "season": 1},
        )
        self.assertIsInstance(obj, Semester)
        self.assertEqual(obj.year, 2031)
        log = CliAuditLog.objects.get(action="create", status="success")
        self.assertEqual(log.target_pk, str(obj.pk))
        self.assertEqual(log.changes["year"], 2031)

    def test_create_rejects_empty_fields(self):
        with self.assertRaises(ActionRequestError):
            cli_create(actor=self.actor, request_ip=None, app_label="projects", model_name="semester", fields={})

    def test_create_rejects_non_dict_fields(self):
        with self.assertRaises(ActionRequestError):
            cli_create(actor=self.actor, request_ip=None, app_label="projects", model_name="semester", fields=[1])

    # ---- update ---------------------------------------------------------
    def _semester(self):
        return cli_create(
            actor=self.actor,
            request_ip=None,
            app_label="projects",
            model_name="semester",
            fields={"year": 2032, "season": 2},
        )

    def test_update_success_records_before_snapshot(self):
        sem = self._semester()
        updated = cli_update(
            actor=self.actor,
            request_ip=None,
            app_label="projects",
            model_name="semester",
            pk=str(sem.pk),
            changes={"is_published": True},
        )
        self.assertTrue(updated.is_published)
        log = CliAuditLog.objects.get(action="update", status="success")
        self.assertIn("is_published", log.before_snapshot)

    def test_update_rejects_empty_changes(self):
        sem = self._semester()
        with self.assertRaises(ActionRequestError):
            cli_update(
                actor=self.actor,
                request_ip=None,
                app_label="projects",
                model_name="semester",
                pk=str(sem.pk),
                changes={},
            )

    def test_update_matching_snapshot_succeeds(self):
        sem = self._semester()
        snapshot = serialize_model_instance(sem, write=True)
        updated = cli_update(
            actor=self.actor,
            request_ip=None,
            app_label="projects",
            model_name="semester",
            pk=str(sem.pk),
            changes={"is_published": True},
            expected_snapshot=snapshot,
        )
        self.assertTrue(updated.is_published)

    def test_update_stale_snapshot_raises(self):
        sem = self._semester()
        with self.assertRaises(StaleSnapshotError):
            cli_update(
                actor=self.actor,
                request_ip=None,
                app_label="projects",
                model_name="semester",
                pk=str(sem.pk),
                changes={"is_published": True},
                expected_snapshot={"year": 1900},
            )

    # ---- delete ---------------------------------------------------------
    def test_delete_zero_cascade(self):
        sem = self._semester()
        result = cli_delete(
            actor=self.actor,
            request_ip=None,
            app_label="projects",
            model_name="semester",
            pk=str(sem.pk),
        )
        self.assertTrue(result["deleted"])
        self.assertEqual(result["cascade"]["total"], 0)
        self.assertFalse(Semester.objects.filter(pk=sem.pk).exists())

    def test_delete_cascade_requires_confirmation(self):
        sem = self._semester()
        Project.objects.create(semester=sem, project_title="Child")
        with self.assertRaises(CascadeNotConfirmedError):
            cli_delete(
                actor=self.actor,
                request_ip=None,
                app_label="projects",
                model_name="semester",
                pk=str(sem.pk),
            )
        self.assertTrue(Semester.objects.filter(pk=sem.pk).exists())

    def test_delete_cascade_with_confirmation(self):
        sem = self._semester()
        Project.objects.create(semester=sem, project_title="Child")
        result = cli_delete(
            actor=self.actor,
            request_ip=None,
            app_label="projects",
            model_name="semester",
            pk=str(sem.pk),
            confirm_cascade=True,
        )
        self.assertGreaterEqual(result["cascade"]["total"], 1)
        self.assertFalse(Semester.objects.filter(pk=sem.pk).exists())
        log = CliAuditLog.objects.get(action="delete", status="success")
        self.assertGreaterEqual(log.cascade["total"], 1)

    def test_delete_stale_snapshot_raises(self):
        sem = self._semester()
        with self.assertRaises(StaleSnapshotError):
            cli_delete(
                actor=self.actor,
                request_ip=None,
                app_label="projects",
                model_name="semester",
                pk=str(sem.pk),
                expected_snapshot={"year": 1900},
            )

    # ---- per-app access -------------------------------------------------
    def test_create_without_app_access_denied(self):
        other = make_admin(apps=["cms"], email="nocreate@example.com")
        with self.assertRaises(CliAppAccessDenied):
            cli_create(
                actor=other,
                request_ip=None,
                app_label="projects",
                model_name="semester",
                fields={"year": 2099, "season": 1},
            )

    def test_update_without_app_access_denied(self):
        sem = self._semester()
        other = make_admin(apps=["cms"], email="noupdate@example.com")
        with self.assertRaises(CliAppAccessDenied):
            cli_update(
                actor=other,
                request_ip=None,
                app_label="projects",
                model_name="semester",
                pk=str(sem.pk),
                changes={"is_published": True},
            )

    def test_delete_without_app_access_denied(self):
        sem = self._semester()
        other = make_admin(apps=["cms"], email="nodelete@example.com")
        with self.assertRaises(CliAppAccessDenied):
            cli_delete(
                actor=other,
                request_ip=None,
                app_label="projects",
                model_name="semester",
                pk=str(sem.pk),
            )
