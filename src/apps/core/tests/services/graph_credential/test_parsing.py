"""Reading the certificate and private key an admin enters: every accepted format, and every refusal on its input."""

import base64
import datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from django.test import SimpleTestCase

from apps.core.services.email.graph.credential import parsing, stored_key
from apps.core.services.email.graph.credential.parsing import (
    parse_certificate_input,
)
from apps.core.tests.graph_helpers import make_certificate, private_key_lines

PASSPHRASE = "not-a-real-passphrase"


def pem(certificate):
    return certificate.public_bytes(serialization.Encoding.PEM).decode()


def key_pem(key, private_format=serialization.PrivateFormat.PKCS8, passphrase=None):
    encryption = serialization.BestAvailableEncryption(passphrase.encode()) if passphrase else None
    return key.private_bytes(
        serialization.Encoding.PEM, private_format, encryption or serialization.NoEncryption()
    ).decode()


def p12(key, certificate, password=PASSPHRASE, *, legacy=False):
    if legacy:
        encryption = (
            serialization.PrivateFormat.PKCS12.encryption_builder()
            .kdf_rounds(2048)
            .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC)
            .hmac_hash(hashes.SHA1())
            .build(password.encode())
        )
    elif password:
        encryption = serialization.BestAvailableEncryption(password.encode())
    else:
        encryption = serialization.NoEncryption()
    return pkcs12.serialize_key_and_certificates(b"i2g", key, certificate, None, encryption)


class AcceptedFormatTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate, cls.key = make_certificate()
        cls.expected_payload = stored_key.key_payload(cls.key)

    def assert_parsed(self, parsed, *, source_format=parsing.PEM_OR_DER):
        self.assertEqual(parsed.facts.sha1_thumbprint, self.certificate.fingerprint(hashes.SHA1()).hex().upper())
        self.assertEqual(parsed.facts.certificate_pem, pem(self.certificate))
        self.assertEqual(parsed.source_format, source_format)
        # Every format of one key re-serialises to the same canonical payload, so storing it again is a no-op.
        self.assertEqual(stored_key.key_payload(parsed.private_key), self.expected_payload)

    def test_pem_certificate_with_pkcs8_and_pkcs1_keys(self):
        for private_format in (serialization.PrivateFormat.PKCS8, serialization.PrivateFormat.TraditionalOpenSSL):
            with self.subTest(private_format=str(private_format)):
                parsed = parse_certificate_input(
                    certificate=pem(self.certificate), private_key=key_pem(self.key, private_format)
                )
                self.assert_parsed(parsed)

    def test_encrypted_pem_keys_with_their_passphrase(self):
        for private_format in (serialization.PrivateFormat.PKCS8, serialization.PrivateFormat.TraditionalOpenSSL):
            with self.subTest(private_format=str(private_format)):
                encrypted = key_pem(self.key, private_format, passphrase=PASSPHRASE)
                parsed = parse_certificate_input(
                    certificate=pem(self.certificate), private_key=encrypted, password=PASSPHRASE
                )
                self.assert_parsed(parsed)

    def test_a_passphrase_given_for_an_unencrypted_key_is_ignored(self):
        parsed = parse_certificate_input(
            certificate=pem(self.certificate), private_key=key_pem(self.key), password=PASSPHRASE
        )
        self.assert_parsed(parsed)

    def test_p12_bundles_modern_legacy_and_without_a_password(self):
        bundles = {
            "aes": (p12(self.key, self.certificate), PASSPHRASE),
            "legacy 3des": (p12(self.key, self.certificate, legacy=True), PASSPHRASE),
            "no password": (p12(self.key, self.certificate, password=""), ""),
        }
        for label, (bundle, password) in bundles.items():
            with self.subTest(label):
                parsed = parse_certificate_input(bundle=bundle, password=password)
                self.assert_parsed(parsed, source_format=parsing.PKCS12)

    def test_certificate_as_der_file_or_header_less_base64(self):
        der = self.certificate.public_bytes(serialization.Encoding.DER)
        for label, value in {"der bytes": der, "base64 text": base64.encodebytes(der).decode()}.items():
            with self.subTest(label):
                self.assert_parsed(parse_certificate_input(certificate=value, private_key=key_pem(self.key)))

    def test_a_der_certificate_ending_in_a_whitespace_byte_is_read_whole(self):
        # About 1 signature in 43 ends in a byte that bytes.strip() removes (space, \t, \n, \v, \f, \r).
        certificates = (make_certificate(key=self.key, serial_number=serial)[0] for serial in range(1, 10_000))
        certificate = next(c for c in certificates if c.public_bytes(serialization.Encoding.DER)[-1:].isspace())

        parsed = parse_certificate_input(
            certificate=certificate.public_bytes(serialization.Encoding.DER), private_key=key_pem(self.key)
        )

        self.assertEqual(parsed.facts.certificate_pem, pem(certificate))

    def test_byte_order_mark_crlf_and_bag_attributes_are_tolerated(self):
        certificate = "﻿" + "Bag Attributes\r\n    friendlyName: i2g\r\n" + pem(self.certificate).replace("\n", "\r\n")

        parsed = parse_certificate_input(
            certificate=certificate.encode("utf-8"), private_key=key_pem(self.key).encode()
        )

        self.assert_parsed(parsed)

    def test_a_combined_key_and_certificate_pem_is_split_in_the_private_key_input(self):
        combined = key_pem(self.key) + "Bag Attributes\n    friendlyName: i2g\n" + pem(self.certificate)
        for label, certificate in {"alone": "", "with the same certificate": pem(self.certificate)}.items():
            with self.subTest(label):
                self.assert_parsed(parse_certificate_input(certificate=certificate, private_key=combined))

    def test_a_certificate_alone_re_issues_the_installed_key(self):
        parsed = parse_certificate_input(certificate=pem(self.certificate))

        self.assertIsNone(parsed.private_key)
        self.assertEqual(parsed.facts.public_key_sha256, self.expected_payload["public_key_sha256"])

    def test_a_start_date_within_the_clock_skew_is_accepted(self):
        certificate, key = make_certificate(not_before_days=60 / 86400)

        parsed = parse_certificate_input(certificate=pem(certificate), private_key=key_pem(key))

        self.assertGreater(parsed.facts.not_before, datetime.datetime.now(datetime.UTC))

    def test_the_parsed_key_is_never_in_the_repr(self):
        parsed = parse_certificate_input(certificate=pem(self.certificate), private_key=key_pem(self.key))

        for line in private_key_lines(self.key):
            self.assertNotIn(line, repr(parsed))
