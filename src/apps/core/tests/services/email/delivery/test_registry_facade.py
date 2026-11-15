from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.services.email import (
    EmailDeliveryService,
    EmailMessage,
    PermanentEmailDeliveryError,
    SMTPProvider,
    deliver_email,
    resolve_provider,
)
from apps.core.services.email.sending.registry import register_provider


class RegistryFacadeTests(SimpleTestCase):
    @patch("apps.core.models.SMTPProviderConfig.load")
    def test_resolves_smtp_config_without_fallback(self, load_smtp):
        load_smtp.return_value = SimpleNamespace(
            is_configured=True,
            host="smtp.example.com",
            port=465,
            username="",
            password="",
            use_tls=False,
            use_ssl=True,
            timeout=10,
        )
        config = SimpleNamespace(
            provider="smtp",
            from_email="from@example.com",
            from_name="Name",
        )
        self.assertIsInstance(resolve_provider(config), SMTPProvider)
        with self.assertRaises(PermanentEmailDeliveryError):
            resolve_provider(SimpleNamespace(provider="unknown"))

    def test_facade_rejects_inactive_config(self):
        message = EmailMessage("Subject", ("to@example.com",), text_body="Body")
        with self.assertRaises(PermanentEmailDeliveryError):
            EmailDeliveryService(SimpleNamespace(is_active=False)).send(message)

    def test_register_provider_rejects_blank_and_duplicate(self):
        with self.assertRaises(ValueError):
            register_provider("   ", lambda config: None)
        with self.assertRaises(ValueError):
            register_provider("smtp", lambda config: None)

    @patch("apps.core.models.SMTPProviderConfig.load")
    def test_smtp_factory_requires_configured_provider(self, load_smtp):
        load_smtp.return_value = SimpleNamespace(is_configured=False)
        with self.assertRaises(PermanentEmailDeliveryError):
            resolve_provider(
                SimpleNamespace(provider="smtp", from_email="from@example.com", from_name=""),
            )

    @patch("apps.core.services.email.sending.delivery.record")
    @patch("apps.core.services.email.sending.delivery.admit")
    @patch("apps.core.services.email.sending.delivery.resolve_provider")
    @patch("apps.core.models.EmailServiceConfig.load")
    def test_delivery_service_loads_config_when_none(self, load_config, resolve, admit, record):
        load_config.return_value = SimpleNamespace(is_active=True, provider="ses")
        provider = MagicMock(rate_channel="ses_send")
        provider.rate_identity.return_value = "1:us-west-2"
        provider.rate_costs.return_value = {}
        provider.send.return_value = MagicMock(message_id="id-1")
        resolve.return_value = provider
        message = EmailMessage("Subject", ("to@example.com",), text_body="Body")

        result = EmailDeliveryService(None).send(message)

        load_config.assert_called_once_with()
        provider.send.assert_called_once()
        self.assertEqual(result.message_id, "id-1")
        admit.assert_called_once_with("ses_send", "1:us-west-2", lane="transactional")
        record.assert_called_once()

    @patch("apps.core.services.email.sending.delivery.EmailDeliveryService")
    def test_deliver_email_delegates_to_service(self, service_cls):
        service = service_cls.return_value
        service.send.return_value = MagicMock(message_id="delegated")
        message = EmailMessage("Subject", ("to@example.com",), text_body="Body")
        config = SimpleNamespace(is_active=True)

        result = deliver_email(message, config=config, configuration_set="events")

        service_cls.assert_called_once_with(config)
        service.send.assert_called_once()
        self.assertEqual(service.send.call_args.kwargs["configuration_set"], "events")
        self.assertEqual(result.message_id, "delegated")
