"""The memory and local-file stores follow the Secrets Manager version and label contract."""

import os
import stat
import sys
import tempfile
from pathlib import Path
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
from apps.core.services.credential_store.local_file import LocalFileStore
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


class LocalFileStoreTests(VersionedStoreContract, SimpleTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "data" / "credential-store"
        self.store = LocalFileStore(root=self.root)

    def mode(self, path):
        return stat.S_IMODE(path.stat().st_mode)

    def test_directories_are_0700_and_files_0600_even_with_an_open_umask(self):
        previous = os.umask(0)
        self.addCleanup(os.umask, previous)
        self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        (secret_dir,) = self.root.iterdir()
        self.assertEqual(self.mode(self.root), 0o700)
        self.assertEqual(self.mode(secret_dir), 0o700)
        self.assertEqual(sorted(path.name for path in secret_dir.iterdir()), sorted([f"{TOKEN}.json", "stages.json"]))
        for path in secret_dir.iterdir():
            self.assertEqual(self.mode(path), 0o600, path.name)

    def test_an_existing_open_directory_is_tightened(self):
        self.root.mkdir(parents=True, mode=0o755)
        os.chmod(self.root, 0o755)
        self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.assertEqual(self.mode(self.root), 0o700)

    def test_settings_select_the_local_directory(self):
        with override_settings(CREDENTIAL_STORE_BACKEND="local_file", CREDENTIAL_STORE_LOCAL_DIR=self.root):
            store = get_store()
            self.assertIsInstance(store, LocalFileStore)
            store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.assertEqual(self.store.read(NAME, arn=f"local-file:{SECRET_ID}", version_id=TOKEN), PAYLOAD)

    def test_filesystem_failures_become_fixed_errors_without_a_chain(self):
        self.root.parent.mkdir(parents=True)
        self.root.write_text("not a directory")
        with self.assertRaises(CredentialStoreError) as failure:
            self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.assert_clean_error(failure.exception)
        self.assertTrue(failure.exception.code.startswith("E"))

    def test_a_symlinked_version_file_is_not_followed(self):
        stored = self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        (secret_dir,) = self.root.iterdir()
        target = secret_dir / f"{TOKEN}.json"
        decoy = Path(self.root.parent) / "decoy.json"
        target.rename(decoy)
        target.symlink_to(decoy)
        with self.assertRaises(CredentialStoreError) as refused:
            self.store.read(NAME, arn=stored.arn, version_id=TOKEN)
        self.assertEqual(refused.exception.code, "ELOOP")

    def test_corrupt_label_file_is_reported_without_its_content(self):
        self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        (secret_dir,) = self.root.iterdir()
        (secret_dir / "stages.json").write_text(f'{{"{TOKEN}": "{MARKER}"}}')
        with self.assertRaises(CredentialStoreError) as corrupt:
            self.store.describe(NAME)
        self.assert_clean_error(corrupt.exception)
        self.assertEqual(corrupt.exception.code, "CorruptStages")

    def test_no_temporary_files_are_left_behind(self):
        self.store.put(NAME, PAYLOAD, version_token=TOKEN)
        self.store.put(NAME, OTHER, version_token=OTHER_TOKEN)
        self.store.move_current(NAME, OTHER_TOKEN)
        leftovers = [path.name for path in self.root.rglob(".*")]
        self.assertEqual(leftovers, [])
