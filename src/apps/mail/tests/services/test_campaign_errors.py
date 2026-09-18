from django.test import SimpleTestCase

from apps.mail.services.campaign.errors import UNEXPECTED_DELIVERY_ERROR, unexpected_delivery_error_message


class UnexpectedDeliveryErrorMessageTests(SimpleTestCase):
    def test_keeps_only_the_exception_class(self):
        exc = ConnectionError("smtp://user:private-value@internal-host/private/path")

        message = unexpected_delivery_error_message(exc)

        self.assertEqual(message, f"{UNEXPECTED_DELIVERY_ERROR} (ConnectionError)")
        self.assertNotIn("private-value", message)
        self.assertNotIn("internal-host", message)

    def test_handles_exceptions_without_text(self):
        self.assertEqual(unexpected_delivery_error_message(KeyError()), f"{UNEXPECTED_DELIVERY_ERROR} (KeyError)")
