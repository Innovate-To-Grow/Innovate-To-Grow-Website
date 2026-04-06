"""Tests for RSA key management service."""

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.test import TestCase

from authn.models import RSAKeypair
from authn.services.rsa_manager import (
    decrypt_password,
    get_or_create_auth_keypair,
    get_public_key_pem,
    is_encrypted_password,
    rotate_auth_keypair,
)


class RSAManagerServiceTests(TestCase):
    # noinspection PyMethodMayBeStatic,PyPep8Naming
    def setUp(self):
        RSAKeypair.objects.all().delete()

    def test_get_public_key_creates_keypair(self):
        pem, key_id = get_public_key_pem()
        self.assertTrue(pem.startswith("-----BEGIN PUBLIC KEY-----"))
        self.assertIsNotNone(key_id)
        self.assertEqual(RSAKeypair.objects.count(), 1)

    def test_get_public_key_is_idempotent(self):
        pem1, kid1 = get_public_key_pem()
        pem2, kid2 = get_public_key_pem()
        self.assertEqual(kid1, kid2)
        self.assertEqual(pem1, pem2)

    def test_encrypt_decrypt_round_trip(self):
        keypair = get_or_create_auth_keypair()
        public_key = serialization.load_pem_public_key(keypair.public_key_pem.encode("utf-8"))

        plaintext = "MySecretPassword123!"
        encrypted = public_key.encrypt(
            plaintext.encode("utf-8"),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")

        decrypted = decrypt_password(encrypted_b64, str(keypair.key_id))
        self.assertEqual(decrypted, plaintext)

    def test_is_encrypted_password_true_for_rsa(self):
        # 256 bytes of random data base64-encoded looks like RSA ciphertext
        fake_ciphertext = base64.b64encode(b"\x00" * 256).decode("utf-8")
        self.assertTrue(is_encrypted_password(fake_ciphertext))

    def test_is_encrypted_password_false_for_plaintext(self):
        self.assertFalse(is_encrypted_password("mypassword"))
        self.assertFalse(is_encrypted_password("short"))
        self.assertFalse(is_encrypted_password(""))

    def test_rotate_keypair_changes_keys(self):
        keypair = get_or_create_auth_keypair()
        old_pem = keypair.public_key_pem

        rotate_auth_keypair(keypair)
        keypair.refresh_from_db()

        self.assertNotEqual(keypair.public_key_pem, old_pem)
        self.assertIsNotNone(keypair.rotated_at)
