"""The service-account key: checking the file in memory, the token test matrix, the store-then-pin order, and the
emergency removal."""

from django.test import TestCase

from apps.core.services.email.gmail.service_account import parsing, stored_key
from apps.core.services.email.gmail.service_account.parsing import KeyInputError, parse_key
from apps.core.tests.gmail_api_helpers import (
    CLIENT_ID,
    KEY_ID,
    SERVICE_ACCOUNT,
    ec_pem,
    key_json,
    pem,
    rsa_key,
)

OTHER_ACCOUNT = "i2g-other@i2g-mail-project.iam.gserviceaccount.com"
OTHER_KEY_ID = bytes(range(20, 40)).hex()  # built at runtime, see gmail_api_helpers.KEY_ID


class KeyParsingTests(TestCase):
    def test_a_console_and_a_gcloud_key_file_both_parse(self):
        for token_uri in parsing.TOKEN_URIS:
            with self.subTest(token_uri=token_uri):
                parsed = parse_key(key_json(token_uri=token_uri))
                self.assertEqual(
                    (parsed.client_email, parsed.client_id, parsed.key_id), (SERVICE_ACCOUNT, CLIENT_ID, KEY_ID)
                )
                self.assertEqual(set(parsed.payload), set(stored_key.PAYLOAD_FIELDS))
                self.assertNotIn("token_uri", parsed.payload)
                self.assertNotIn("PRIVATE", repr(parsed))

    def test_bytes_with_a_byte_order_mark_parse(self):
        self.assertEqual(parse_key(b"\xef\xbb\xbf" + key_json().encode()).key_id, KEY_ID)

    def test_the_validation_matrix_refuses_with_fixed_text(self):
        duplicate = key_json()[:-1] + ', "type": "service_account"}'
        cases = {
            "not json": ("{nope", parsing.NOT_JSON),
            "NaN": (key_json().replace('"googleapis.com"', "NaN"), parsing.NOT_JSON),
            "duplicate": (duplicate, parsing.DUPLICATE_FIELD),
            "array": ("[]", parsing.NOT_OBJECT),
            "oversize": ("x" * 16_385, parsing.TOO_LARGE),
            "not utf-8": (b"\xff\xfe{}", parsing.NOT_TEXT),
            "authorized user": (key_json(type="authorized_user"), parsing.NOT_SERVICE_ACCOUNT),
            "external account": (key_json(type="external_account"), parsing.NOT_SERVICE_ACCOUNT),
            "missing client_id": (key_json(client_id=None), parsing.MISSING_FIELD.format(field="client_id")),
            "missing key": (key_json(private_key=None), parsing.MISSING_FIELD.format(field="private_key")),
            "ec key": (key_json(private_key=ec_pem()), "Google service-account keys are RSA keys"),
            "1024-bit key": (key_json(private_key=pem(rsa_key(1024))), "smaller than the site accepts"),
            "encrypted key": (key_json(private_key=pem(password=b"passphrase-x")), "could not be read"),
            "other token_uri": (key_json(token_uri="https://evil.example/token"), parsing.BAD_TOKEN_URI),
            "not a service account": (key_json(client_email="me@gmail.com"), parsing.BAD_EMAIL),
            "compute account": (key_json(client_email="123-compute@developer.gserviceaccount.com"), parsing.BAD_EMAIL),
            "project mismatch": (key_json(project_id="another-project"), parsing.PROJECT_MISMATCH),
            "domain-scoped": (key_json(project_id="example.com:i2g"), parsing.DOMAIN_SCOPED),
            "client id": (key_json(client_id="12ab"), parsing.BAD_CLIENT_ID),
            "key id": (key_json(private_key_id="XYZ"), parsing.BAD_KEY_ID),
            "universe": (key_json(universe_domain="example.com"), parsing.BAD_UNIVERSE),
        }
        for name, (data, message) in cases.items():
            with self.subTest(name), self.assertRaises(KeyInputError) as caught:
                parse_key(data)
            self.assertIn(message, caught.exception.message)
            self.assertIsNone(caught.exception.__cause__)

    def test_no_message_contains_the_submitted_text(self):
        secret = "SENTINEL-super-secret-value"
        for data in (key_json(client_id=secret), key_json(token_uri=secret), f'{{"{secret}": 1, "{secret}": 2}}'):
            with self.subTest(data=data[:40]), self.assertRaises(KeyInputError) as caught:
                parse_key(data)
            self.assertNotIn(secret, str(caught.exception))
