"""The service-account assertion: RS256, the key id, the claims Google documents, and the keys it accepts."""

import jwt
from django.test import SimpleTestCase, override_settings

from apps.core.services.email.gmail import assertion
from apps.core.services.email.gmail.assertion import GMAIL_SEND_SCOPE, TOKEN_URI, SigningKeyError, load_signing_key
from apps.core.tests.gmail_api_helpers import KEY_ID, SERVICE_ACCOUNT, SUBJECT, ec_pem, pem, rsa_key


class AssertionTests(SimpleTestCase):
    def build(self, **overrides):
        options = {"client_email": SERVICE_ACCOUNT, "key_id": KEY_ID, "private_key": rsa_key(), "subject": SUBJECT}
        options.update(overrides)
        return assertion.build_assertion(**options)

    def test_header_names_rs256_and_the_key_id(self):
        header = jwt.get_unverified_header(self.build())
        self.assertEqual(header, {"alg": "RS256", "typ": "JWT", "kid": KEY_ID})

    def test_claims_and_signature(self):
        token = self.build()
        claims = jwt.decode(token, rsa_key().public_key(), algorithms=["RS256"], audience=TOKEN_URI)
        self.assertEqual(claims["iss"], SERVICE_ACCOUNT)
        self.assertEqual(claims["sub"], SUBJECT)
        self.assertEqual(claims["scope"], GMAIL_SEND_SCOPE)
        self.assertEqual(claims["aud"], "https://oauth2.googleapis.com/token")
        self.assertEqual(claims["exp"] - claims["iat"], 300)
        self.assertEqual(set(claims), {"iss", "sub", "scope", "aud", "iat", "exp"})

    @override_settings(GMAIL_API={"assertion_lifetime_seconds": 120, "min_rsa_key_bits": 2048})
    def test_lifetime_comes_from_settings(self):
        claims = jwt.decode(self.build(), options={"verify_signature": False})
        self.assertEqual(claims["exp"] - claims["iat"], 120)

    def test_another_key_does_not_verify(self):
        with self.assertRaises(jwt.InvalidSignatureError):
            jwt.decode(self.build(), rsa_key(3072).public_key(), algorithms=["RS256"], audience=TOKEN_URI)


class SigningKeyTests(SimpleTestCase):
    def test_an_unencrypted_rsa_key_of_2048_bits_loads(self):
        self.assertEqual(load_signing_key(pem()).key_size, 2048)

    def test_ec_small_encrypted_and_unreadable_keys_are_refused_with_fixed_text(self):
        cases = (
            (ec_pem(), assertion.RSA_ONLY),
            (pem(rsa_key(1024)), assertion.KEY_TOO_SMALL),
            (pem(password=b"secret-passphrase"), assertion.UNREADABLE_KEY),
            ("-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----\n", assertion.UNREADABLE_KEY),
            ("ключ", assertion.UNREADABLE_KEY),
            (None, assertion.UNREADABLE_KEY),
        )
        for value, message in cases:
            with self.subTest(message=message), self.assertRaises(SigningKeyError) as caught:
                load_signing_key(value)
            self.assertEqual(str(caught.exception), message)
            self.assertIsNone(caught.exception.__cause__)
