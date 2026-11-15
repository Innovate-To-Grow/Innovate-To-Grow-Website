"""The shared safe-ORM denylist keeps the Gmail API config and its impersonation allow-list away from the assistant
and the CLI: either would let a caller widen which Workspace users the site may send as."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.models import GmailApiProviderConfig, GmailApiSubject
from apps.core.services.db_tools.safe_orm import DENIED_MODEL_LABELS, ActionRequestError, is_model_denied, resolve_model

GMAIL_MODELS = (GmailApiProviderConfig, GmailApiSubject)
SAFETY = "apps.core.services.db_tools.safe_orm.safety"


class GmailApiModelDenylistTest(SimpleTestCase):
    def test_both_models_are_listed_and_denied_for_read_and_write(self):
        for model in GMAIL_MODELS:
            self.assertIn(model._meta.label_lower, DENIED_MODEL_LABELS)
            for write, access in ((False, "Read"), (True, "Write")):
                with self.subTest(model=model.__name__, write=write):
                    self.assertTrue(is_model_denied(model, write=write))
                    with self.assertRaises(ActionRequestError) as error:
                        resolve_model("core", model._meta.model_name, write=write)
                    self.assertEqual(str(error.exception), f"{access} access is not allowed for core.{model.__name__}.")

    def test_only_the_explicit_label_blocks_the_allow_list(self):
        with patch(f"{SAFETY}.DENIED_MODEL_LABELS", frozenset()):
            self.assertFalse(is_model_denied(GmailApiSubject, write=True))
