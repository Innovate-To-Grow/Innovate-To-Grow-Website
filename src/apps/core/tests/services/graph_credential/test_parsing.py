"""Reading the certificate and private key an admin enters: every accepted format, and every refusal on its input."""

import base64
import datetime
from unittest.mock import Mock, patch

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from django.test import SimpleTestCase, override_settings

from apps.core.services.email.graph.credential import loaders, parsing, stored_key
from apps.core.services.email.graph.credential.parsing import (
    BUNDLE,
    CERTIFICATE,
    PASSWORD,
    PRIVATE_KEY,
    CertificateInputError,
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


class RefusedInputTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate, cls.key = make_certificate()
        cls.leaked = private_key_lines(cls.key)

    def assert_refused(self, field, message, **inputs):
        with self.assertRaises(CertificateInputError) as caught:
            parse_certificate_input(**inputs)
        self.assertEqual((caught.exception.field, caught.exception.message), (field, message))
        self.assertIsNone(caught.exception.__cause__)
        for line in self.leaked:
            self.assertNotIn(line, str(caught.exception))
        return caught.exception

    def test_a_private_key_in_the_certificate_input_is_refused(self):
        for label, value in {
            "key + certificate": key_pem(self.key) + pem(self.certificate),
            "certificate + key": pem(self.certificate) + key_pem(self.key),
            "key alone": key_pem(self.key),
        }.items():
            with self.subTest(label):
                self.assert_refused(CERTIFICATE, loaders.KEY_IN_CERTIFICATE, certificate=value)

    def test_more_than_one_certificate_is_refused(self):
        other, _ = make_certificate()

        self.assert_refused(
            CERTIFICATE,
            loaders.ONE_CERTIFICATE,
            certificate=pem(self.certificate) + pem(other),
            private_key=key_pem(self.key),
        )

    def test_the_private_key_input_must_hold_one_key_and_at_most_its_certificate(self):
        other, _ = make_certificate()
        cases = {
            "only a certificate": (loaders.CERTIFICATE_IN_KEY, pem(self.certificate)),
            "two keys": (loaders.ONE_KEY, key_pem(self.key) * 2),
            "two certificates": (loaders.ONE_KEY, key_pem(self.key) + pem(self.certificate) + pem(other)),
            "garbage": (loaders.UNREADABLE_KEY, "not a key"),
        }
        for label, (message, value) in cases.items():
            with self.subTest(label):
                self.assert_refused(PRIVATE_KEY, message, certificate=pem(self.certificate), private_key=value)

    def test_a_combined_pem_with_another_certificate_is_refused(self):
        other, _ = make_certificate()

        self.assert_refused(
            PRIVATE_KEY,
            parsing.DIFFERENT_CERTIFICATES,
            certificate=pem(other),
            private_key=key_pem(self.key) + pem(self.certificate),
        )

    def test_a_key_from_another_certificate_is_refused(self):
        other, _ = make_certificate(key_index=1)

        self.assert_refused(PRIVATE_KEY, parsing.KEY_MISMATCH, certificate=pem(other), private_key=key_pem(self.key))

    def test_non_rsa_keys_and_certificates_are_refused(self):
        ec_certificate, ec_key = make_certificate(ec_key=True)
        traditional = key_pem(ec_key, serialization.PrivateFormat.TraditionalOpenSSL)

        self.assert_refused(PRIVATE_KEY, loaders.RSA_ONLY, certificate=pem(self.certificate), private_key=traditional)
        self.assert_refused(
            PRIVATE_KEY, loaders.RSA_ONLY, certificate=pem(self.certificate), private_key=key_pem(ec_key)
        )
        self.assert_refused(CERTIFICATE, loaders.RSA_ONLY, certificate=pem(ec_certificate))

    def test_keys_below_the_configured_size_are_refused(self):
        small, small_key = make_certificate(key_size=1024)
        self.assert_refused(
            CERTIFICATE,
            "The certificate's RSA key must be at least 2048 bits.",
            certificate=pem(small),
            private_key=key_pem(small_key),
        )
        with override_settings(GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS=3072):
            self.assert_refused(
                CERTIFICATE,
                "The certificate's RSA key must be at least 3072 bits.",
                certificate=pem(self.certificate),
                private_key=key_pem(self.key),
            )

    def test_expired_and_not_yet_valid_certificates_are_refused(self):
        expired, expired_key = make_certificate(days_valid=-1, not_before_days=-30)
        future, future_key = make_certificate(not_before_days=2)

        self.assert_refused(CERTIFICATE, parsing.EXPIRED, certificate=pem(expired), private_key=key_pem(expired_key))
        self.assert_refused(
            CERTIFICATE, parsing.NOT_YET_VALID, certificate=pem(future), private_key=key_pem(future_key)
        )
        self.assert_refused(BUNDLE, parsing.EXPIRED, bundle=p12(expired_key, expired), password=PASSPHRASE)

    def test_passphrases_are_required_and_checked(self):
        encrypted = key_pem(self.key, passphrase=PASSPHRASE)
        certificate = pem(self.certificate)

        self.assert_refused(PASSWORD, loaders.KEY_NEEDS_PASSPHRASE, certificate=certificate, private_key=encrypted)
        self.assert_refused(
            PASSWORD, loaders.WRONG_PASSPHRASE, certificate=certificate, private_key=encrypted, password="wrong"
        )

    def test_bundles_need_their_password_and_both_parts(self):
        self.assert_refused(PASSWORD, loaders.UNOPENED_BUNDLE, bundle=p12(self.key, self.certificate), password="wrong")
        self.assert_refused(PASSWORD, loaders.UNOPENED_BUNDLE, bundle=b"not a bundle")
        certificate_only = pkcs12.serialize_key_and_certificates(
            b"i2g", None, self.certificate, None, serialization.NoEncryption()
        )
        self.assert_refused(BUNDLE, loaders.INCOMPLETE_BUNDLE, bundle=certificate_only)

    def test_a_bundle_and_separate_parts_together_are_refused(self):
        self.assert_refused(
            BUNDLE, parsing.BUNDLE_OR_PARTS, bundle=p12(self.key, self.certificate), certificate=pem(self.certificate)
        )

    def test_blank_and_unreadable_inputs(self):
        self.assert_refused(CERTIFICATE, parsing.CERTIFICATE_REQUIRED)
        self.assert_refused(CERTIFICATE, parsing.CERTIFICATE_REQUIRED, private_key="  \n")
        for value in (
            "not a certificate",
            b"\x30\x03garbage",
            "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----",
        ):
            with self.subTest(value=value):
                self.assert_refused(CERTIFICATE, loaders.UNREADABLE_CERTIFICATE, certificate=value)
        self.assert_refused(CERTIFICATE, loaders.NOT_TEXT, certificate="caf\xe9")

    @override_settings(GRAPH_CERTIFICATE_MAX_INPUT_BYTES=100)
    def test_oversized_inputs_are_refused_before_parsing(self):
        self.assert_refused(PRIVATE_KEY, parsing.TOO_LARGE, certificate="x", private_key=key_pem(self.key))
        self.assert_refused(BUNDLE, parsing.TOO_LARGE, bundle=b"x" * 101)

    def test_unsupported_algorithms_become_field_errors_instead_of_server_errors(self):
        with patch.object(loaders.x509, "load_pem_x509_certificate", side_effect=UnsupportedAlgorithm("sm2")):
            self.assert_refused(CERTIFICATE, loaders.UNREADABLE_CERTIFICATE, certificate=pem(self.certificate))
        with patch.object(loaders.serialization, "load_pem_private_key", side_effect=UnsupportedAlgorithm("sm2")):
            self.assert_refused(
                PRIVATE_KEY, loaders.RSA_ONLY, certificate=pem(self.certificate), private_key=key_pem(self.key)
            )
        unloadable = Mock(public_key=Mock(side_effect=UnsupportedAlgorithm("sm2")))
        with patch.object(loaders.x509, "load_pem_x509_certificate", return_value=unloadable):
            self.assert_refused(CERTIFICATE, loaders.RSA_ONLY, certificate=pem(self.certificate))
