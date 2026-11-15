from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.models import (
    SMTPProviderConfig,
)


class SMTPProviderConfigTest(TestCase):
    def test_load_does_not_fall_back_to_inactive_config(self):
        SMTPProviderConfig.objects.create(name="Inactive", host="smtp.example.com")

        loaded = SMTPProviderConfig.load()

        self.assertTrue(loaded._state.adding)
        self.assertFalse(loaded.is_configured)

    def test_activation_deactivates_existing_config(self):
        first = SMTPProviderConfig.objects.create(name="First", host="one.example.com", is_active=True)
        second = SMTPProviderConfig.objects.create(name="Second", host="two.example.com", is_active=True)

        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(SMTPProviderConfig.load(), second)

    def test_rejects_tls_and_ssl_together(self):
        config = SMTPProviderConfig(host="smtp.example.com", use_tls=True, use_ssl=True)

        with self.assertRaises(ValidationError):
            config.save()

    def test_database_still_rejects_two_active_configurations(self):
        SMTPProviderConfig.objects.create(name="Primary", host="smtp.example.com", is_active=True)
        standby = SMTPProviderConfig.objects.create(name="Standby", host="backup.example.com")

        with self.assertRaises(IntegrityError), transaction.atomic():
            SMTPProviderConfig.objects.filter(pk=standby.pk).update(is_active=True)

        self.assertEqual(SMTPProviderConfig.objects.filter(is_active=True).count(), 1)

    def test_blank_or_invalid_port_is_a_validation_error(self):
        for port in (None, "", "invalid", 0, 65536):
            with self.subTest(port=port), self.assertRaises(ValidationError) as error:
                SMTPProviderConfig(host="smtp.example.com", port=port).full_clean()
            self.assertIn("port", error.exception.message_dict)

    def test_rejects_partial_credentials(self):
        config = SMTPProviderConfig(host="smtp.example.com", username="user")

        with self.assertRaises(ValidationError):
            config.save()

    def test_str_never_contains_credentials(self):
        config = SMTPProviderConfig(
            name="Mail", host="smtp.example.com", username="secret-user", password="secret-password"
        )

        rendered = str(config)
        self.assertIn("smtp.example.com:587", rendered)
        self.assertNotIn("secret-user", rendered)
        self.assertNotIn("secret-password", rendered)
