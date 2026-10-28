"""The shared safe-ORM denylist keeps Microsoft Graph credentials away from the assistant and the CLI."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.models import MicrosoftGraphProviderConfig
from apps.core.services.db_tools.safe_orm import (
    DENIED_MODEL_LABELS,
    SENSITIVE_FIELD_RE,
    ActionRequestError,
    field_output_name,
    is_field_denied,
    is_model_denied,
    resolve_model,
    safe_model_fields,
)

LABEL = "core.microsoftgraphproviderconfig"
SAFETY = "apps.core.services.db_tools.safe_orm.safety"


class GraphModelDenylistTest(SimpleTestCase):
    def test_label_is_listed_explicitly_and_matches_the_model(self):
        self.assertIn(LABEL, DENIED_MODEL_LABELS)
        self.assertEqual(MicrosoftGraphProviderConfig._meta.label_lower, LABEL)

    def test_model_is_denied_for_read_and_write(self):
        for write in (False, True):
            with self.subTest(write=write):
                self.assertTrue(is_model_denied(MicrosoftGraphProviderConfig, write=write))

    def test_resolve_model_refuses_read_and_write(self):
        for write, access in ((False, "Read"), (True, "Write")):
            for model_name in ("microsoftgraphproviderconfig", "MicrosoftGraphProviderConfig"):
                with self.subTest(write=write, model_name=model_name):
                    with self.assertRaises(ActionRequestError) as error:
                        resolve_model("core", model_name, write=write)

                    self.assertEqual(
                        str(error.exception), f"{access} access is not allowed for core.MicrosoftGraphProviderConfig."
                    )

    def test_explicit_label_blocks_the_model_without_the_name_rule(self):
        # The name rule ("config" in the model name) already catches this model; the label is the second line
        # of defence, so remove the name rule and check the label alone still refuses it.
        with patch(f"{SAFETY}.DENIED_MODEL_NAME_PARTS", ()):
            for write in (False, True):
                with self.subTest(write=write):
                    self.assertTrue(is_model_denied(MicrosoftGraphProviderConfig, write=write))

            # Control: with the label gone as well, nothing else denies it, so the label is what protects it.
            with patch(f"{SAFETY}.DENIED_MODEL_LABELS", frozenset()):
                self.assertFalse(is_model_denied(MicrosoftGraphProviderConfig, write=False))
                self.assertFalse(is_model_denied(MicrosoftGraphProviderConfig, write=True))


class GraphFieldDenylistTest(SimpleTestCase):
    def test_client_secret_matches_the_sensitive_field_pattern(self):
        self.assertTrue(SENSITIVE_FIELD_RE.search("client_secret"))

    def test_client_secret_is_denied_for_read_and_write(self):
        field = MicrosoftGraphProviderConfig._meta.get_field("client_secret")

        for write in (False, True):
            with self.subTest(write=write):
                self.assertTrue(is_field_denied(field, write=write))

    def test_client_secret_is_never_among_the_safe_fields(self):
        for write in (False, True):
            with self.subTest(write=write):
                names = {field_output_name(f) for f in safe_model_fields(MicrosoftGraphProviderConfig, write=write)}

                self.assertNotIn("client_secret", names)
