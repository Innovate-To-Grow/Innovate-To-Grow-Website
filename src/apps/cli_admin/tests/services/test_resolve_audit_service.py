import uuid

from django.apps import apps as django_apps
from django.test import TestCase

from apps.cli_admin.auth.constants import CLI_EXTRA_DENIED_MODEL_LABELS
from apps.cli_admin.services.audit import write_audit
from apps.cli_admin.services.resolve import cli_get_object, resolve_cli_model
from apps.core.services.db_tools.safe_orm import ActionRequestError, is_model_denied
from apps.event.tests.helpers import make_member
from apps.projects.models import Semester


class ResolveServiceTests(TestCase):
    def test_resolve_ok(self):
        self.assertIs(resolve_cli_model("projects", "semester", write=True), Semester)

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

    def test_every_table_the_cli_keeps_from_itself_is_write_denied_to_the_assistant_too(self):
        # The shared layer also serves the admin assistant's record writes. A table the CLI keeps out of its own reach
        # (its sign-in codes and tokens, its audit log, login links, invitations) must not be writable there either:
        # a written authorization code is a CLI session as whoever it names.
        for label in sorted(CLI_EXTRA_DENIED_MODEL_LABELS):
            with self.subTest(label=label):
                self.assertTrue(is_model_denied(django_apps.get_model(label), write=True))


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
