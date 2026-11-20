"""The shared safe-ORM denylist keeps the universal inbox's per-account state away from the assistant and the CLI:
its snapshot holds the senders, subjects and previews of every inbox account's newest messages."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.cli_admin.services.resolve import resolve_cli_model
from apps.core.services.db_tools.safe_orm import DENIED_MODEL_LABELS, ActionRequestError, is_model_denied, resolve_model
from apps.mail.models import InboxAccountState

SAFETY = "apps.core.services.db_tools.safe_orm.safety"


class InboxAccountStateDenylistTest(SimpleTestCase):
    def test_listed_explicitly(self):
        self.assertIn("mail.inboxaccountstate", DENIED_MODEL_LABELS)
        self.assertEqual(InboxAccountState._meta.label_lower, "mail.inboxaccountstate")

    def test_resolve_model_refuses_read_and_write(self):
        for write, access in ((False, "Read"), (True, "Write")):
            for model_name in (InboxAccountState._meta.model_name, InboxAccountState.__name__):
                with self.subTest(write=write, model_name=model_name):
                    self.assertTrue(is_model_denied(InboxAccountState, write=write))
                    with self.assertRaises(ActionRequestError) as error:
                        resolve_model("mail", model_name, write=write)

                    self.assertEqual(
                        str(error.exception), f"{access} access is not allowed for mail.InboxAccountState."
                    )

    def test_the_cli_refuses_it_too(self):
        for write in (False, True):
            with self.subTest(write=write), self.assertRaises(ActionRequestError):
                resolve_cli_model("mail", "inboxaccountstate", write=write)

    def test_only_the_explicit_label_blocks_it(self):
        # Its name matches no denied name part ("config", "token", ...).
        with patch(f"{SAFETY}.DENIED_MODEL_LABELS", frozenset()):
            self.assertFalse(is_model_denied(InboxAccountState, write=False))
            self.assertFalse(is_model_denied(InboxAccountState, write=True))
