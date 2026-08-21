"""Coverage for service-credential model properties and helpers."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.models import (
    AWSCredentialConfig,
    EmailServiceConfig,
    GmailAccessAccount,
    GoogleCredentialConfig,
    SMTPProviderConfig,
)
from apps.core.models.base.service_credentials.google import validate_google_credentials_json

VALID_GOOGLE_JSON = {
    "type": "service_account",
    "project_id": "proj-1",
    "private_key": "fake-key",  # noqa: S106 — test fixture
    "client_email": "svc@proj.iam.gserviceaccount.com",
    "token_uri": "https://oauth2.googleapis.com/token",
}


class AwsConfigPropertiesTest(TestCase):
    def test_load_does_not_fall_back_to_inactive_credentials(self):
        AWSCredentialConfig.objects.create(
            name="Inactive",
            access_key_id="K",
            secret_access_key="S",
            is_active=False,
        )

        loaded = AWSCredentialConfig.load()

        self.assertIsNone(loaded.pk)
        self.assertFalse(loaded.is_configured)

    def test_ses_configured_mirrors_is_configured(self):
        configured = AWSCredentialConfig(access_key_id="K", secret_access_key="S")
        self.assertTrue(configured.ses_configured)
        self.assertFalse(AWSCredentialConfig().ses_configured)

    def test_render_sms_otp_uses_default_template(self):
        config = AWSCredentialConfig()
        message = config.render_sms_otp_message("123456")
        self.assertIn("123456", message)
        self.assertIn("verification code", message)

    def test_render_sms_otp_uses_custom_template(self):
        config = AWSCredentialConfig(sms_message_template="Code: {code}")
        self.assertEqual(config.render_sms_otp_message("999"), "Code: 999")

    def test_render_sms_otp_rejects_template_without_placeholder(self):
        config = AWSCredentialConfig(sms_message_template="No placeholder here")
        with self.assertRaises(ValueError):
            config.render_sms_otp_message("123")


class EmailConfigTest(TestCase):
    def test_load_does_not_fall_back_to_inactive_sender(self):
        EmailServiceConfig.objects.create(
            name="Inactive",
            from_email="stale@example.com",
            is_active=False,
        )

        loaded = EmailServiceConfig.load()

        self.assertIsNone(loaded.pk)
        self.assertNotEqual(loaded.from_email, "stale@example.com")

    def test_str_configured_and_unconfigured(self):
        AWSCredentialConfig.objects.create(name="AWS", is_active=True, access_key_id="K", secret_access_key="S")
        configured = EmailServiceConfig.objects.create(name="Prod", is_active=True)
        self.assertIn("AWS SES (active)", str(configured))

    def test_str_unconfigured(self):
        AWSCredentialConfig.objects.all().delete()
        config = EmailServiceConfig(name="Dev")
        self.assertIn("not configured", str(config))

    def test_source_address_with_name(self):
        config = EmailServiceConfig(from_name="I2G", from_email="x@y.com")
        self.assertEqual(config.source_address, "I2G <x@y.com>")

    def test_source_address_without_name(self):
        config = EmailServiceConfig(from_name="", from_email="x@y.com")
        self.assertEqual(config.source_address, "x@y.com")

    def test_ses_configured_reads_aws(self):
        AWSCredentialConfig.objects.create(name="AWS", is_active=True, access_key_id="K", secret_access_key="S")
        config = EmailServiceConfig.objects.create(name="P", is_active=True)
        self.assertTrue(config.ses_configured)

    def test_ses_configured_fails_closed_without_active_sender(self):
        AWSCredentialConfig.objects.create(name="AWS", is_active=True, access_key_id="K", secret_access_key="S")
        self.assertFalse(EmailServiceConfig(name="P").ses_configured)

    def test_activation_validation_requires_selected_provider(self):
        smtp_config = EmailServiceConfig(
            name="SMTP",
            is_active=True,
            provider=EmailServiceConfig.Provider.SMTP,
            from_email="sender@example.com",
        )
        with self.assertRaises(ValidationError):
            smtp_config.validate_activation()

        ses_config = EmailServiceConfig(
            name="SES",
            is_active=True,
            provider=EmailServiceConfig.Provider.SES,
            from_email="sender@example.com",
        )
        with self.assertRaises(ValidationError):
            ses_config.validate_activation()


class GmailConfigTest(TestCase):
    def test_load_does_not_fall_back_to_inactive_credentials(self):
        GmailAccessAccount.objects.create(name="Older", gmail_username="a@x.com")
        GmailAccessAccount.objects.create(name="Newer", gmail_username="b@x.com")

        loaded = GmailAccessAccount.load()

        self.assertIsNone(loaded.pk)
        self.assertFalse(loaded.is_configured)


class GoogleConfigTest(TestCase):
    def test_validate_rejects_non_dict(self):
        with self.assertRaises(ValidationError):
            validate_google_credentials_json(["not", "a", "dict"])

    def test_validate_rejects_missing_fields(self):
        with self.assertRaises(ValidationError) as cm:
            validate_google_credentials_json({"type": "service_account"})
        self.assertIn("Missing required fields", str(cm.exception))

    def test_validate_accepts_full_json(self):
        # Should not raise.
        validate_google_credentials_json(VALID_GOOGLE_JSON)

    def test_str_with_and_without_credentials(self):
        with_creds = GoogleCredentialConfig(name="G", credentials_json=VALID_GOOGLE_JSON)
        self.assertIn("proj-1", str(with_creds))
        empty = GoogleCredentialConfig(name="G", credentials_json={})
        self.assertIn("empty", str(empty))

    def test_load_does_not_fall_back_to_inactive_credentials(self):
        GoogleCredentialConfig.objects.create(name="Older", credentials_json=VALID_GOOGLE_JSON)
        GoogleCredentialConfig.objects.create(name="Newer", credentials_json=VALID_GOOGLE_JSON)

        loaded = GoogleCredentialConfig.load()

        self.assertIsNone(loaded.pk)
        self.assertFalse(loaded.is_configured)

    def test_get_credentials_info(self):
        config = GoogleCredentialConfig(credentials_json=VALID_GOOGLE_JSON)
        self.assertEqual(config.get_credentials_info(), VALID_GOOGLE_JSON)
        self.assertEqual(GoogleCredentialConfig(credentials_json={}).get_credentials_info(), {})

    def test_is_configured(self):
        self.assertTrue(GoogleCredentialConfig(credentials_json=VALID_GOOGLE_JSON).is_configured)
        self.assertFalse(GoogleCredentialConfig(credentials_json={}).is_configured)


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
