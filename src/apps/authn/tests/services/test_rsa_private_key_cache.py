"""Parsed RSA private keys are reused across decrypts, while the key row is still checked on every call."""

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.authn.models import RSAKeypair
from apps.authn.services.security import key_encryption, rsa_manager
from apps.authn.services.security.rsa_manager import (
    KEY_DECRYPTION_GRACE_PERIOD,
    KEY_PURGE_RETENTION,
    RSADecryptionError,
    decrypt_password,
    get_or_create_auth_keypair,
    purge_retired_auth_keypairs,
    rotate_auth_keypair,
)

OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
PLAINTEXT = "CachedKeyPassword1!"


def encrypt_for(public_key_pem: str, plaintext: str = PLAINTEXT) -> str:
    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    return base64.b64encode(public_key.encrypt(plaintext.encode("utf-8"), OAEP)).decode("utf-8")


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class PrivateKeyCacheTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        rsa_manager.clear_private_key_cache()
        self.addCleanup(rsa_manager.clear_private_key_cache)
        RSAKeypair.objects.all().delete()
        self.keypair = get_or_create_auth_keypair()
        self.key_id = str(self.keypair.key_id)
        self.ciphertext = encrypt_for(self.keypair.public_key_pem)

    def parses(self):
        """Count the expensive step: parsing the PEM (it runs the RSA key consistency check)."""
        return patch.object(serialization, "load_pem_private_key", wraps=serialization.load_pem_private_key)

    def test_repeated_decrypts_parse_and_unwrap_the_key_once(self):
        with (
            self.parses() as parse,
            patch.object(key_encryption, "decrypt_pem", wraps=key_encryption.decrypt_pem) as unwrap,
        ):
            results = [decrypt_password(self.ciphertext, self.key_id) for _ in range(5)]

        self.assertEqual(results, [PLAINTEXT] * 5)
        self.assertEqual(parse.call_count, 1)
        self.assertEqual(unwrap.call_count, 1)

    def test_the_active_key_path_without_a_key_id_shares_the_cached_key(self):
        with self.parses() as parse:
            self.assertEqual(decrypt_password(self.ciphertext), PLAINTEXT)
            self.assertEqual(decrypt_password(self.ciphertext, self.key_id), PLAINTEXT)

        self.assertEqual(parse.call_count, 1)

    def test_every_decrypt_still_reads_the_key_row(self):
        decrypt_password(self.ciphertext, self.key_id)

        with CaptureQueriesContext(connection) as queries:
            decrypt_password(self.ciphertext, self.key_id)

        self.assertEqual(len(queries.captured_queries), 1)
        self.assertIn(RSAKeypair._meta.db_table, queries.captured_queries[0]["sql"])

    def test_new_material_under_the_same_key_id_is_parsed_again_and_the_old_key_is_gone(self):
        decrypt_password(self.ciphertext, self.key_id)
        public_pem, private_pem = RSAKeypair.generate_keypair()
        RSAKeypair.objects.filter(pk=self.keypair.pk).update(
            public_key_pem=public_pem,
            private_key_pem=key_encryption.encrypt_pem(private_pem),
        )

        with self.parses() as parse:
            self.assertEqual(decrypt_password(encrypt_for(public_pem), self.key_id), PLAINTEXT)
            with self.assertRaises(RSADecryptionError):
                decrypt_password(self.ciphertext, self.key_id)  # the replaced key must not decrypt from the cache

        self.assertEqual(parse.call_count, 1)
        self.assertEqual([key_id for key_id, _fingerprint in rsa_manager._private_keys], [self.key_id])

    def test_rotation_parses_the_new_key_and_keeps_the_retired_one_usable_during_its_grace(self):
        decrypt_password(self.ciphertext, self.key_id)
        replacement = rotate_auth_keypair(self.keypair)

        with self.parses() as parse:
            self.assertEqual(decrypt_password(encrypt_for(replacement.public_key_pem)), PLAINTEXT)
            self.assertEqual(decrypt_password(self.ciphertext, self.key_id), PLAINTEXT)

        self.assertEqual(parse.call_count, 1)  # only the new key

    def test_a_retired_key_past_its_grace_cannot_decrypt_even_when_cached(self):
        decrypt_password(self.ciphertext, self.key_id)
        rotate_auth_keypair(self.keypair)
        RSAKeypair.objects.filter(pk=self.keypair.pk).update(
            rotated_at=timezone.now() - KEY_DECRYPTION_GRACE_PERIOD - timedelta(seconds=1)
        )

        with self.parses() as parse, self.assertRaisesMessage(RSADecryptionError, "has expired"):
            decrypt_password(self.ciphertext, self.key_id)
        parse.assert_not_called()

    def test_a_purged_key_cannot_decrypt_even_when_cached(self):
        decrypt_password(self.ciphertext, self.key_id)
        rotate_auth_keypair(self.keypair)
        RSAKeypair.objects.filter(pk=self.keypair.pk).update(
            rotated_at=timezone.now() - KEY_PURGE_RETENTION - timedelta(seconds=1)
        )
        self.assertEqual(purge_retired_auth_keypairs(), 1)

        with self.parses() as parse, self.assertRaisesMessage(RSADecryptionError, "Unknown RSA key identifier"):
            decrypt_password(self.ciphertext, self.key_id)
        parse.assert_not_called()

    def test_a_different_secret_key_misses_the_cache(self):
        """A SECRET_KEY that can no longer unwrap the stored key must not keep decrypting through the cache."""
        decrypt_password(self.ciphertext, self.key_id)

        with (
            override_settings(SECRET_KEY="a-rotated-secret-key-for-this-test"),
            self.assertRaisesMessage(RSADecryptionError, "Has SECRET_KEY changed?"),
        ):
            decrypt_password(self.ciphertext, self.key_id)

    def test_entries_expire_after_the_ttl(self):
        clock = Clock()
        with patch.object(rsa_manager, "_monotonic", clock), self.parses() as parse:
            decrypt_password(self.ciphertext, self.key_id)
            clock.now += rsa_manager._PRIVATE_KEY_CACHE_TTL_SECONDS - 1
            decrypt_password(self.ciphertext, self.key_id)
            self.assertEqual(parse.call_count, 1)

            clock.now += 1
            decrypt_password(self.ciphertext, self.key_id)

        self.assertEqual(parse.call_count, 2)

    def test_expired_entries_are_dropped_whichever_key_is_used_next(self):
        clock = Clock()
        replacement = rotate_auth_keypair(self.keypair)
        with patch.object(rsa_manager, "_monotonic", clock):
            decrypt_password(self.ciphertext, self.key_id)
            clock.now += rsa_manager._PRIVATE_KEY_CACHE_TTL_SECONDS
            decrypt_password(encrypt_for(replacement.public_key_pem))

        self.assertEqual([key_id for key_id, _fingerprint in rsa_manager._private_keys], [str(replacement.key_id)])

    def test_the_cache_holds_at_most_eight_keys_and_drops_the_least_recently_used(self):
        public_pem, private_pem = RSAKeypair.generate_keypair()
        keypairs = [
            RSAKeypair.objects.create(
                name="cache-bound-test", public_key_pem=public_pem, private_key_pem=private_pem, is_active=False
            )
            for _ in range(10)
        ]

        with self.parses() as parse:
            for keypair in keypairs:
                rsa_manager._load_private_key(keypair)
            rsa_manager._load_private_key(keypairs[-1])  # still cached
            self.assertEqual(parse.call_count, 10)
            rsa_manager._load_private_key(keypairs[0])  # evicted: parsed again

        self.assertEqual(parse.call_count, 11)
        self.assertEqual(len(rsa_manager._private_keys), rsa_manager._PRIVATE_KEY_CACHE_SIZE)
        self.assertEqual(rsa_manager._PRIVATE_KEY_CACHE_SIZE, 8)

    def test_the_cache_is_keyed_on_ids_and_fingerprints_never_key_material(self):
        decrypt_password(self.ciphertext, self.key_id)

        ((key_id, fingerprint),) = rsa_manager._private_keys
        self.assertEqual(key_id, self.key_id)
        self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")
        self.assertNotIn(fingerprint, self.keypair.private_key_pem)

    def test_concurrent_loads_of_one_key_agree(self):
        keypair = RSAKeypair.objects.get(pk=self.keypair.pk)

        with ThreadPoolExecutor(max_workers=8) as pool:
            keys = list(pool.map(lambda _index: rsa_manager._load_private_key(keypair), range(32)))

        self.assertEqual(len(rsa_manager._private_keys), 1)
        numbers = {key.private_numbers().d for key in keys}
        self.assertEqual(len(numbers), 1)
