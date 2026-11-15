"""The memory and local-file stores follow the Secrets Manager version and label contract."""

import sys
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.views.debug import ExceptionReporter

from apps.core.services.credential_store import (
    CURRENT_STAGE,
    PREVIOUS_STAGE,
    CredentialStoreError,
    get_store,
    version_token_for,
)
from apps.core.services.credential_store import memory as memory_store
from apps.core.services.credential_store.memory import MemoryStore

NAME = "microsoft_graph_certificate_key"
SECRET_ID = "itg/backend/microsoft-graph/certificate-key"
MARKER = "do-not-echo-" + "k" * 40
PAYLOAD = {"schema": "test/1", "private_key_pem": MARKER, "public_key_sha256": "a" * 64}
OTHER = {"schema": "test/1", "private_key_pem": MARKER + "-other", "public_key_sha256": "b" * 64}
TOKEN = version_token_for(NAME, "a" * 64)
OTHER_TOKEN = version_token_for(NAME, "b" * 64)
STAGED = "I2G-STAGED"


class VersionedStoreContract:
    """Runs against every in-process store; subclasses set ``self.store`` in setUp."""

    def stages(self):
        return dict(self.store.describe(NAME).version_stages)

    def assert_clean_error(self, error):
        self.assertNotIn(MARKER, str(error))
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)

    def test_first_version_becomes_current_and_later_versions_are_only_staged(self):
        first = self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.assertEqual(first.arn, f"{self.store.scheme}:{SECRET_ID}")
        self.assertEqual(first.version_id, TOKEN)
        self.assertEqual(self.stages(), {TOKEN: (STAGED, CURRENT_STAGE)})

        self.store.put(NAME, OTHER, version_token=OTHER_TOKEN)
        self.assertEqual(self.stages(), {TOKEN: (CURRENT_STAGE,), OTHER_TOKEN: (STAGED,)})
        self.assertEqual(self.store.describe(NAME).current_version_id, TOKEN)

    def test_reads_are_pinned_to_the_named_version(self):
        stored = self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.store.put(NAME, OTHER, version_token=OTHER_TOKEN)
        self.assertEqual(self.store.read(NAME, arn=stored.arn, version_id=TOKEN), PAYLOAD)
        self.assertEqual(self.store.read(NAME, arn=stored.arn, version_id=OTHER_TOKEN), OTHER)
        with self.assertRaises(CredentialStoreError) as missing:
            self.store.read(NAME, arn=stored.arn, version_id=version_token_for(NAME, "c" * 64))
        self.assertEqual(missing.exception.code, "ResourceNotFoundException")
        for version_id in ("", "AWSCURRENT", None):
            with self.subTest(version_id=version_id), self.assertRaises(CredentialStoreError):
                self.store.read(NAME, arn=stored.arn, version_id=version_id)

    def test_same_token_and_payload_is_a_no_op_but_a_different_payload_is_refused(self):
        self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.store.put(NAME, OTHER, version_token=OTHER_TOKEN)
        before = self.stages()
        again = self.store.put(NAME, dict(reversed(list(PAYLOAD.items()))), version_token=TOKEN)
        self.assertEqual(again.version_id, TOKEN)
        self.assertEqual(self.stages(), before)

        with self.assertRaises(CredentialStoreError) as conflict:
            self.store.put(NAME, OTHER, version_token=TOKEN)
        self.assert_clean_error(conflict.exception)
        self.assertEqual(self.store.read(NAME, arn=again.arn, version_id=TOKEN), PAYLOAD)

    def test_moving_current_hands_previous_to_the_old_holder_and_rolls_back(self):
        self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.store.put(NAME, OTHER, version_token=OTHER_TOKEN)
        self.assertTrue(self.store.move_current(NAME, OTHER_TOKEN))
        self.assertEqual(self.stages(), {TOKEN: (PREVIOUS_STAGE,), OTHER_TOKEN: (STAGED, CURRENT_STAGE)})
        self.assertTrue(self.store.move_current(NAME, OTHER_TOKEN))
        self.assertTrue(self.store.move_current(NAME, TOKEN))
        self.assertEqual(self.stages(), {TOKEN: (CURRENT_STAGE,), OTHER_TOKEN: (STAGED, PREVIOUS_STAGE)})

    def test_moving_current_to_an_unknown_version_is_logged_and_reported(self):
        self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        with self.assertLogs("apps.core.services.credential_store.versioned", level="WARNING"):
            self.assertFalse(self.store.move_current(NAME, OTHER_TOKEN))
        self.assertEqual(self.store.describe(NAME).current_version_id, TOKEN)

    def test_foreign_references_and_unconfigured_names_are_refused(self):
        stored = self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        for arn in (f"other:{SECRET_ID}", stored.arn + "x", "arn:aws:secretsmanager:us-west-2:1:secret:x-AbCdEf"):
            with self.subTest(arn=arn), self.assertRaises(CredentialStoreError):
                self.store.read(NAME, arn=arn, version_id=TOKEN)
        with self.assertRaises(CredentialStoreError):
            self.store.put("gmail_service_account_key", PAYLOAD, version_token=TOKEN)
        with override_settings(CREDENTIAL_STORE_SECRETS={NAME: "itg/backend/aws-credentials/graph"}):
            with self.assertRaises(CredentialStoreError):
                self.store.put(NAME, PAYLOAD, version_token=TOKEN)

    def test_invalid_payloads_and_tokens_are_refused_with_fixed_text(self):
        for payload in ({}, [MARKER], {"key": MARKER.encode()}, {"key": float("nan")}, {1: MARKER}):
            with self.subTest(payload=type(payload).__name__), self.assertRaises(CredentialStoreError) as refused:
                self.store.put(NAME, payload, version_token=TOKEN)
            self.assert_clean_error(refused.exception)
        for token in ("short", "x" * 65, "not a/token" * 4, None):
            with self.subTest(token=token), self.assertRaises(CredentialStoreError):
                self.store.put(NAME, PAYLOAD, version_token=token)
        with override_settings(CREDENTIAL_STORE_MAX_PAYLOAD_BYTES=64), self.assertRaises(CredentialStoreError):
            self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.assertEqual(self.store.describe(NAME).version_stages, ())

    def test_error_reports_hide_the_payload_in_every_store_frame(self):
        with patch.object(type(self.store), "_write_version", side_effect=RuntimeError("disk gone")):
            try:
                self.store.put(NAME, PAYLOAD, version_token=TOKEN)
            except RuntimeError:
                frames = ExceptionReporter(None, *sys.exc_info()).get_traceback_frames()
        store_frames = [frame for frame in frames if "/apps/core/services/credential_store/" in frame["filename"]]
        self.assertTrue(store_frames)
        self.assertNotIn(MARKER, repr([frame["vars"] for frame in store_frames]))


class MemoryStoreTests(VersionedStoreContract, SimpleTestCase):
    def setUp(self):
        memory_store.reset()
        self.addCleanup(memory_store.reset)
        self.store = MemoryStore()

    def test_test_settings_select_the_shared_memory_store(self):
        self.assertIsInstance(get_store(), MemoryStore)
        get_store().put(NAME, PAYLOAD, version_token=TOKEN)
        self.assertEqual(get_store().describe(NAME).current_version_id, TOKEN)
