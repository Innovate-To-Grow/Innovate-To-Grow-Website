"""Coverage for SES transport helpers."""

from django.test import TestCase, override_settings

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.mail.services.campaign.send.transport import (
    _build_raw_ses_message,
    _build_unsubscribe_headers,
    _get_configuration_set_name,
    _get_ses_client,
)


class GetSesClientTests(TestCase):
    def test_returns_none_when_ses_not_configured(self):
        config = EmailServiceConfig(is_active=False)
        self.assertIsNone(_get_ses_client(config))

    def test_builds_client_with_resolved_credentials(self):
        AWSCredentialConfig.objects.all().delete()
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        config = EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
        )

        result = _get_ses_client(config)

        self.assertIsNotNone(result)
        self.assertIs(result, config)

    def _active_aws(self):
        AWSCredentialConfig.objects.all().delete()
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )

    def test_returns_none_when_aws_credentials_error(self):
        self._active_aws()
        config = EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
        )
        AWSCredentialConfig.objects.all().delete()
        self.assertIsNone(_get_ses_client(config))

    def test_returns_none_on_unexpected_error(self):
        self._active_aws()
        config = EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
        )
        config.provider = "unknown"
        self.assertFalse(config.delivery_configured)
        self.assertIsNone(_get_ses_client(config))


class ConfigurationSetNameTests(TestCase):
    def test_prefers_config_attribute(self):
        config = EmailServiceConfig()
        # The model has no such field; the source reads it via getattr, so we set
        # it dynamically to exercise the "prefer config attribute" branch.
        config.ses_configuration_set_name = "  cfg-set  "
        self.assertEqual(_get_configuration_set_name(config), "cfg-set")

    @override_settings(SES_CONFIGURATION_SET_NAME="settings-set")
    def test_falls_back_to_settings(self):
        config = EmailServiceConfig()
        self.assertEqual(_get_configuration_set_name(config), "settings-set")


class UnsubscribeHeaderTests(TestCase):
    def test_empty_url_returns_no_headers(self):
        self.assertEqual(_build_unsubscribe_headers(""), {})

    def test_url_returns_rfc8058_headers(self):
        headers = _build_unsubscribe_headers("https://example.com/u")
        self.assertEqual(headers["List-Unsubscribe"], "<https://example.com/u>")
        self.assertEqual(headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")


class BuildRawMessageTests(TestCase):
    def test_includes_extra_headers(self):
        raw = _build_raw_ses_message(
            source="from@example.com",
            recipient="to@example.com",
            subject="Hi",
            html_body="<p>Hi</p>",
            extra_headers={"List-Unsubscribe": "<https://example.com/u>"},
        )

        self.assertIn("List-Unsubscribe: <https://example.com/u>", raw)
        self.assertIn("Subject: Hi", raw)
