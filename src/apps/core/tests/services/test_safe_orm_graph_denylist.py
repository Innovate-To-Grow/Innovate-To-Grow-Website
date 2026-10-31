"""The shared safe-ORM denylist keeps the Microsoft Graph config, its mailbox scope and its installed certificates
away from the assistant and the CLI."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.services.db_tools.safe_orm import DENIED_MODEL_LABELS, ActionRequestError, is_model_denied, resolve_model

GRAPH_MODELS = (MicrosoftGraphProviderConfig, MicrosoftGraphMailboxScope, MicrosoftGraphCertificate)
SAFETY = "apps.core.services.db_tools.safe_orm.safety"


class GraphModelDenylistTest(SimpleTestCase):
    def test_every_graph_model_is_listed_explicitly(self):
        for model in GRAPH_MODELS:
            with self.subTest(model=model.__name__):
                self.assertIn(model._meta.label_lower, DENIED_MODEL_LABELS)

    def test_every_graph_model_is_denied_for_read_and_write(self):
        for model in GRAPH_MODELS:
            for write in (False, True):
                with self.subTest(model=model.__name__, write=write):
                    self.assertTrue(is_model_denied(model, write=write))

    def test_resolve_model_refuses_read_and_write(self):
        for model in GRAPH_MODELS:
            for write, access in ((False, "Read"), (True, "Write")):
                for model_name in (model._meta.model_name, model.__name__):
                    with self.subTest(write=write, model_name=model_name):
                        with self.assertRaises(ActionRequestError) as error:
                            resolve_model("core", model_name, write=write)

                        self.assertEqual(
                            str(error.exception), f"{access} access is not allowed for core.{model.__name__}."
                        )

    def test_the_explicit_label_is_what_blocks_the_scope_and_certificate_models(self):
        # Their names match no denied name part ("config", "credential", ...), so only the label protects them.
        for model in (MicrosoftGraphMailboxScope, MicrosoftGraphCertificate):
            with self.subTest(model=model.__name__), patch(f"{SAFETY}.DENIED_MODEL_LABELS", frozenset()):
                self.assertFalse(is_model_denied(model, write=False))
                self.assertFalse(is_model_denied(model, write=True))

    def test_the_config_label_blocks_it_without_the_name_rule(self):
        # The name rule ("config" in the model name) already catches this model; the label is the second line
        # of defence, so remove the name rule and check the label alone still refuses it.
        with patch(f"{SAFETY}.DENIED_MODEL_NAME_PARTS", ()):
            for write in (False, True):
                with self.subTest(write=write):
                    self.assertTrue(is_model_denied(MicrosoftGraphProviderConfig, write=write))
