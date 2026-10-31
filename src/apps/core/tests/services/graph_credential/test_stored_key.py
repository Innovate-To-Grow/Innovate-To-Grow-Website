"""The Graph key in the credential store: canonical payload, idempotent writes and verified, pinned reads."""

from django.test import SimpleTestCase, override_settings

from apps.core.services.credential_store import CredentialStoreError, get_store, memory, version_token_for
from apps.core.services.email.graph.certificate import public_key_sha256
from apps.core.services.email.graph.credential import stored_key
from apps.core.services.email.graph.credential.stored_key import StoredKeyMismatch, key_payload, read_key, store_key
from apps.core.tests.graph_helpers import make_certificate, private_key_lines
from apps.core.tests.services.graph_credential.helpers import stored_versions


class StoredKeyTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        memory.reset()
        self.addCleanup(memory.reset)
        _certificate, self.key = make_certificate()
        self.public_hash = public_key_sha256(self.key.public_key())

    def test_the_payload_is_pkcs8_plus_the_public_key_hash_and_nothing_else(self):
        payload = key_payload(self.key)

        self.assertEqual(set(payload), {"schema", "private_key_pem", "public_key_sha256"})
        self.assertEqual(payload["schema"], stored_key.PAYLOAD_SCHEMA)
        self.assertTrue(payload["private_key_pem"].startswith("-----BEGIN PRIVATE KEY-----"))
        self.assertEqual(payload["public_key_sha256"], self.public_hash)

    def test_storing_the_same_key_twice_is_one_version_named_after_the_key(self):
        first = store_key(self.key)
        second = store_key(self.key)

        self.assertEqual(first, second)
        self.assertEqual(first.version_id, version_token_for(stored_key.KEY_NAME, self.public_hash))
        self.assertEqual(list(stored_versions()), [first.version_id])
        for line in private_key_lines(self.key):
            self.assertNotIn(line, repr(first))

    def test_a_pinned_read_returns_the_key(self):
        stored = store_key(self.key)

        key = read_key(arn=stored.arn, version_id=stored.version_id, expected_public_key_sha256=self.public_hash)

        self.assertEqual(key.private_numbers(), self.key.private_numbers())

    def test_reads_that_do_not_match_the_certificate_fail_closed(self):
        stored = store_key(self.key)
        _other_certificate, other_key = make_certificate(key_index=1)
        for label, expected in {"another hash": public_key_sha256(other_key.public_key()), "blank": ""}.items():
            with self.subTest(label):
                with self.assertRaises(StoredKeyMismatch):
                    read_key(arn=stored.arn, version_id=stored.version_id, expected_public_key_sha256=expected)

    def test_unexpected_payloads_are_never_used(self):
        payloads = {
            "wrong schema": {**key_payload(self.key), "schema": "other/1"},
            "hash of another key": {**key_payload(self.key), "public_key_sha256": "0" * 64},
            "unreadable key": {**key_payload(self.key), "private_key_pem": "not a key"},
            "missing key": {"schema": stored_key.PAYLOAD_SCHEMA, "public_key_sha256": self.public_hash},
        }
        for index, (label, payload) in enumerate(payloads.items()):
            with self.subTest(label):
                token = version_token_for(stored_key.KEY_NAME, f"test-{index}")
                stored = get_store().put(stored_key.KEY_NAME, payload, version_token=token)

                with self.assertRaises(StoredKeyMismatch) as caught:
                    read_key(arn=stored.arn, version_id=stored.version_id, expected_public_key_sha256=self.public_hash)

                self.assertEqual(
                    str(caught.exception), "The stored private key does not match the installed certificate."
                )

    @override_settings(CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER=True)
    def test_an_environment_that_requires_secrets_manager_refuses_other_stores(self):
        with self.assertRaises(CredentialStoreError):
            store_key(self.key)
        self.assertEqual(stored_versions(), {})
