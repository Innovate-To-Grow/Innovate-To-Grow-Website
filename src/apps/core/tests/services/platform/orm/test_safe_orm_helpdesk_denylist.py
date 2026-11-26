"""The shared safe-ORM denylist keeps the helpdesk away from the assistant and the CLI, read and write: every helpdesk
model (people's mail, its tickets and their configuration) is listed, and a table Django creates for one of them (the
assignment group's members: which member is in which group) is denied with it. A table Django creates for a model
that is not denied stays readable."""

from django.apps import apps
from django.test import SimpleTestCase, tag

from apps.authn.models import Member
from apps.cli_admin.services.resolve import resolve_cli_model
from apps.core.services.db_tools.safe_orm import DENIED_MODEL_LABELS, ActionRequestError, is_model_denied, resolve_model
from apps.helpdesk.models import AssignmentGroup


@tag("safe_orm")
class HelpdeskDenylistTest(SimpleTestCase):
    def test_every_helpdesk_model_is_listed(self):
        labels = {model._meta.label_lower for model in apps.get_app_config("helpdesk").get_models()}

        self.assertIn("helpdesk.ticket", labels)
        self.assertEqual(labels - DENIED_MODEL_LABELS, set())

    def test_the_tables_django_creates_for_them_are_denied_read_and_write(self):
        models = apps.get_app_config("helpdesk").get_models(include_auto_created=True)
        created = [model for model in models if model._meta.auto_created]

        self.assertIn(AssignmentGroup.members.through, created)
        for model in created:
            for write, access in ((False, "Read"), (True, "Write")):
                with self.subTest(model=model._meta.label, write=write):
                    self.assertTrue(is_model_denied(model, write=write))
                    with self.assertRaises(ActionRequestError) as error:
                        resolve_model("helpdesk", model.__name__, write=write)
                    self.assertEqual(str(error.exception), f"{access} access is not allowed for {model._meta.label}.")

    def test_the_cli_refuses_them_too(self):
        for model_name in ("ticket", "assignmentgroup", "assignmentgroup_members"):
            for write in (False, True):
                with self.subTest(model_name=model_name, write=write), self.assertRaises(ActionRequestError):
                    resolve_cli_model("helpdesk", model_name, write=write)

    def test_a_table_django_creates_for_a_model_that_is_not_denied_stays_readable(self):
        self.assertFalse(is_model_denied(Member.groups.through, write=False))
