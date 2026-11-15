import os
import stat
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from apps.core.services.credential_store import (
    CredentialStoreError,
    get_store,
)
from apps.core.services.credential_store.local_file import LocalFileStore
from apps.core.tests.services.credential_store.test_versioned_stores import (
    MARKER,
    NAME,
    OTHER,
    OTHER_TOKEN,
    PAYLOAD,
    SECRET_ID,
    TOKEN,
    VersionedStoreContract,
)


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
