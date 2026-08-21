"""Coverage for SES transport helpers."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.email import (
    DeliveryResult,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.mail.services.send_campaign.transport import (
    SES_OUTCOME_PERMANENT,
    SES_OUTCOME_TRANSIENT,
    SES_OUTCOME_UNCERTAIN,
    SesSendResult,
    _build_raw_ses_message,
    _build_unsubscribe_headers,
    _get_configuration_set_name,
    _get_ses_client,
    _send_via_ses,
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


class SendViaSesTests(TestCase):
    def _send(self, side_effect=None, result=None, **overrides):
        config = MagicMock(provider="ses")
        with patch("apps.mail.services.send_campaign.transport.deliver_email") as deliver:
            deliver.side_effect = side_effect
            deliver.return_value = result or DeliveryResult(provider="ses", message_id="SES-1")
            send_result = _send_via_ses(
                ses_client=config,
                source="from@example.com",
                recipient="to@example.com",
                subject="Hi",
                html_body="<p>Hi</p>",
                **overrides,
            )
        return send_result, deliver

    def test_success_returns_message_id(self):
        result, deliver = self._send(
            unsubscribe_url="https://example.com/u",
            configuration_set="cfg",
        )

        self.assertEqual(result.message_id, "SES-1")
        self.assertEqual(result.error, "")
        self.assertEqual(deliver.call_args.kwargs["configuration_set"], "cfg")

    def test_failure_returns_error(self):
        result, _ = self._send(side_effect=UncertainEmailDeliveryError("could not be confirmed"))

        self.assertEqual(result.outcome, SES_OUTCOME_UNCERTAIN)
        self.assertIn("could not be confirmed", result.error)
        self.assertEqual(result.message_id, "")

    def test_throttle_response_is_definitive_transient(self):
        result, _ = self._send(side_effect=TransientEmailDeliveryError("slow down"))

        self.assertEqual(result.outcome, SES_OUTCOME_TRANSIENT)

    def test_access_denied_response_is_definitive_permanent(self):
        result, _ = self._send(side_effect=PermanentEmailDeliveryError("denied"))

        self.assertEqual(result.outcome, SES_OUTCOME_PERMANENT)

    def test_endpoint_connection_failure_is_safe_to_retry(self):
        result, _ = self._send(side_effect=TransientEmailDeliveryError("endpoint unavailable"))

        self.assertEqual(result.outcome, SES_OUTCOME_TRANSIENT)

    def test_send_via_ses_omits_configuration_set_when_empty(self):
        _, deliver = self._send()
        self.assertEqual(deliver.call_args.kwargs["configuration_set"], "")


class SesSendResultTests(TestCase):
    def test_defaults(self):
        result = SesSendResult()
        self.assertEqual(result.provider, "ses")
        self.assertEqual(result.message_id, "")
        self.assertEqual(result.error, "")
        self.assertEqual(result.outcome, "success")
