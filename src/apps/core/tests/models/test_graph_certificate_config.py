"""Certificate authentication on ``MicrosoftGraphProviderConfig``: validation, recorded metadata and readiness."""

import datetime

from cryptography.hazmat.primitives import serialization
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import MicrosoftGraphProviderConfig
from apps.core.services.email.graph.certificate import inspect_pair
from apps.core.tests.graph_helpers import certificate_pair, grant

AuthMethod = MicrosoftGraphProviderConfig.AuthMethod
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def certificate_config(*, is_active=True, certificate=None, private_key=None, **overrides):
    if certificate is None and private_key is None:
        certificate, private_key = certificate_pair()
    return MicrosoftGraphProviderConfig(
        name="Graph",
        is_active=is_active,
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        auth_method=AuthMethod.CERTIFICATE,
        certificate=certificate or "",
        private_key=private_key or "",
        **overrides,
    )


def encrypted(key_pem):
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(b"not-a-real-passphrase"),
    ).decode()


class CertificateCleanTests(TestCase):
    def assert_error(self, config, field, message):
        with self.assertRaises(ValidationError) as caught:
            config.full_clean()
        self.assertIn(message, " ".join(caught.exception.message_dict.get(field, [])))
        return caught.exception

    def test_new_configs_default_to_certificate_auth(self):
        self.assertEqual(MicrosoftGraphProviderConfig().auth_method, AuthMethod.CERTIFICATE)

    def test_a_valid_pair_records_thumbprint_and_expiry(self):
        certificate, key = certificate_pair(days_valid=200)
        config = certificate_config(certificate=f"\n{certificate}\n", private_key=f"{key}\n  ")

        config.save()

        config.refresh_from_db()
        info = inspect_pair(certificate, key)
        self.assertEqual(config.certificate_thumbprint, info.thumbprint)
        self.assertEqual(config.certificate_expires_at, info.not_after)
        self.assertEqual(config.certificate, certificate.strip())
        self.assertEqual(config.private_key, key.strip())
        self.assertFalse(config.certificate_expired)

    def test_a_mismatched_key_is_refused(self):
        certificate, _ = certificate_pair()
        _, other_key = certificate_pair(key_size=3072)

        self.assert_error(
            certificate_config(certificate=certificate, private_key=other_key), "certificate", "does not belong"
        )

    def test_an_ec_key_is_refused(self):
        certificate, key = certificate_pair(ec_key=True)

        self.assert_error(certificate_config(certificate=certificate, private_key=key), "certificate", "RSA key")

    def test_a_1024_bit_key_is_refused(self):
        certificate, key = certificate_pair(key_size=1024)

        self.assert_error(certificate_config(certificate=certificate, private_key=key), "certificate", "2048 bits")

    def test_an_encrypted_key_is_refused_without_echoing_key_material(self):
        certificate, key = certificate_pair()
        locked = encrypted(key)

        error = self.assert_error(
            certificate_config(certificate=certificate, private_key=locked), "certificate", "password-protected"
        )
        self.assertNotIn(locked.splitlines()[1], str(error))

    def test_an_expired_certificate_is_refused_while_active(self):
        certificate, key = certificate_pair(days_valid=-1, not_before_days=-30)

        self.assert_error(certificate_config(certificate=certificate, private_key=key), "certificate", "has expired")

    def test_an_expired_certificate_may_be_stored_on_a_standby_config(self):
        certificate, key = certificate_pair(days_valid=-1, not_before_days=-30)
        config = certificate_config(is_active=False, certificate=certificate, private_key=key)

        config.save()

        self.assertTrue(config.certificate_expired)
        self.assertTrue(config.certificate_thumbprint)

    def test_one_half_of_the_pair_is_not_enough(self):
        certificate, key = certificate_pair()
        for is_active in (True, False):
            with self.subTest(is_active=is_active):
                self.assert_error(
                    certificate_config(is_active=is_active, certificate=certificate, private_key=""),
                    "private_key",
                    "Enter both",
                )
                self.assert_error(
                    certificate_config(is_active=is_active, certificate="", private_key=key),
                    "certificate",
                    "Enter both",
                )

    def test_an_active_config_needs_a_pair(self):
        config = certificate_config(certificate="", private_key="")
        config.certificate = config.private_key = ""

        self.assert_error(config, "certificate", "certificate and its private key are required")

    def test_a_standby_config_may_leave_the_pair_blank(self):
        config = certificate_config(is_active=False, certificate="", private_key="")
        config.certificate = config.private_key = ""

        config.save()

        self.assertEqual((config.certificate_thumbprint, config.certificate_expires_at), ("", None))

    def test_unreadable_pem_is_refused(self):
        _, key = certificate_pair()

        self.assert_error(certificate_config(certificate="garbage", private_key=key), "certificate", "readable PEM")

    def test_metadata_is_reset_when_the_pair_is_removed(self):
        config = certificate_config(is_active=False)
        config.save()
        self.assertTrue(config.certificate_thumbprint)

        config.certificate = config.private_key = ""
        config.save()

        self.assertEqual((config.certificate_thumbprint, config.certificate_expires_at), ("", None))

    def test_client_secret_method_needs_a_secret_when_active(self):
        config = certificate_config(certificate="", private_key="")
        config.auth_method = AuthMethod.CLIENT_SECRET

        self.assert_error(config, "client_secret", "client secret is required")

        config.client_secret = "not-a-real-secret"
        config.full_clean()


class CertificateReadinessTests(TestCase):
    def test_a_certificate_config_with_a_scope_is_configured(self):
        config = certificate_config()
        config.save()
        grant(config, "i2g@contoso.com")

        self.assertTrue(config.uses_certificate)
        self.assertTrue(config.credential_configured)
        self.assertTrue(config.is_configured)
        self.assertTrue(config.sending_ready("i2g@contoso.com"))

    def test_an_expired_certificate_is_not_configured(self):
        config = certificate_config()
        config.save()
        grant(config, "i2g@contoso.com")
        past = timezone.now() - datetime.timedelta(minutes=1)
        MicrosoftGraphProviderConfig.objects.filter(pk=config.pk).update(certificate_expires_at=past)
        config.refresh_from_db()

        self.assertTrue(config.certificate_expired)
        self.assertFalse(config.credential_configured)
        self.assertFalse(config.is_configured)

    def test_a_certificate_config_without_its_thumbprint_or_key_is_not_configured(self):
        config = certificate_config()
        config.save()
        grant(config, "i2g@contoso.com")
        for field in ("certificate_thumbprint", "private_key", "certificate"):
            with self.subTest(field):
                config.refresh_from_db()
                setattr(config, field, "")
                self.assertFalse(config.credential_configured)

    def test_the_client_secret_does_not_satisfy_the_certificate_method(self):
        config = certificate_config(is_active=False, certificate="", private_key="", client_secret="leftover")

        self.assertFalse(config.credential_configured)
        config.auth_method = AuthMethod.CLIENT_SECRET
        self.assertTrue(config.credential_configured)
        self.assertFalse(config.uses_certificate)

    def test_no_expiry_is_not_expired(self):
        self.assertFalse(MicrosoftGraphProviderConfig().certificate_expired)
