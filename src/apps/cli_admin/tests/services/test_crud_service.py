import uuid

from django.test import TestCase

from apps.cli_admin.models import CliAuditLog
from apps.cli_admin.services.audit import write_audit
from apps.cli_admin.services.crud import (
    CascadeNotConfirmedError,
    StaleSnapshotError,
    cli_create,
    cli_delete,
    cli_update,
)
from apps.cli_admin.services.resolve import CliAppAccessDenied, cli_get_object, resolve_cli_model
from apps.core.services.db_tools.safe_orm import ActionRequestError, serialize_model_instance
from apps.event.tests.helpers import make_admin, make_member, make_superuser
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


class ResolveServiceTests(TestCase):
    def test_resolve_ok(self):
        self.assertIs(resolve_cli_model("projects", "semester", write=True), Semester)

    def test_resolve_no_actor_skips_app_access_check(self):
        # actor=None (the default) is the metadata path: only the denylist applies.
        self.assertIs(resolve_cli_model("projects", "semester", write=False), Semester)

    def test_resolve_granted_actor_ok(self):
        actor = make_admin(apps=["projects"], email="granted@example.com")
        self.assertIs(resolve_cli_model("projects", "semester", write=True, actor=actor), Semester)

    def test_resolve_ungranted_actor_raises_app_access_denied(self):
        actor = make_admin(apps=["cms"], email="ungranted@example.com")
        with self.assertRaises(CliAppAccessDenied) as ctx:
            resolve_cli_model("projects", "semester", write=False, actor=actor)
        self.assertIn("projects", str(ctx.exception))

    def test_resolve_superuser_actor_bypasses_app_access(self):
        actor = make_superuser(email="super@example.com")
        self.assertIs(resolve_cli_model("projects", "semester", write=True, actor=actor), Semester)

    def test_resolve_denylist_precedes_app_access_check(self):
        # A denied model raises the plain ActionRequestError (→400), never the
        # 403 CliAppAccessDenied, even for an actor lacking the app.
        actor = make_admin(apps=["cms"], email="denyfirst@example.com")
        with self.assertRaises(ActionRequestError) as ctx:
            resolve_cli_model("authn", "member", write=False, actor=actor)
        self.assertNotIsInstance(ctx.exception, CliAppAccessDenied)

    def test_resolve_extra_denied_read(self):
        with self.assertRaises(ActionRequestError):
            resolve_cli_model("cli_admin", "cliauthorizationcode", write=False)

    def test_resolve_extra_denied_write(self):
        with self.assertRaises(ActionRequestError):
            resolve_cli_model("cli_admin", "cliauthorizationcode", write=True)

    def test_resolve_app_denied_read(self):
        with self.assertRaises(ActionRequestError):
            resolve_cli_model("authn", "member", write=False)

    def test_resolve_app_denied_write(self):
        with self.assertRaises(ActionRequestError):
            resolve_cli_model("authn", "member", write=True)

    def test_cli_get_object_missing_propagates_doesnotexist(self):
        with self.assertRaises(Semester.DoesNotExist):
            cli_get_object(Semester, str(uuid.uuid4()))

    def test_cli_get_object_bad_pk_raises_action_error(self):
        with self.assertRaises(ActionRequestError):
            cli_get_object(Semester, "not-a-valid-uuid")


class AuditServiceTests(TestCase):
    def test_write_audit_truncates_repr(self):
        actor = make_member(email="audit@example.com")
        log = write_audit(
            actor=actor,
            action="create",
            status="success",
            app_label="projects",
            model_name="semester",
            target_repr="x" * 500,
        )
        self.assertEqual(len(log.target_repr), 300)
