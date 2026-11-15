from concurrent.futures import ThreadPoolExecutor

from apps.authn.models import RSAKeypair
from apps.authn.services.security import rsa_manager
from apps.authn.services.security.decryption import decrypt_password
from apps.authn.tests.services.security.rsa.test_rsa_private_key_cache import _PrivateKeyCacheCase


class PrivateKeyCacheTests(_PrivateKeyCacheCase):
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
