from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.services.email import (
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.graph import provider as graph_provider
from apps.core.tests.services.graph.provider.test_email_graph import GraphFixtureMixin, make_provider, simple_message


class GraphCompositionTests(GraphFixtureMixin, SimpleTestCase):
    def assert_nothing_happened(self, callback):
        """Composition problems are definitive: no token request, no HTTP call, no callback."""
        self.assertEqual(self.fake.requests, [])
        callback.assert_not_called()

    def test_bcc_recipients_are_rejected_before_any_network_activity(self):
        callback = MagicMock()

        with self.assertRaisesMessage(PermanentEmailDeliveryError, "Bcc"):
            make_provider().send(simple_message(bcc=("hidden@example.com",)), before_provider_call=callback)

        self.assert_nothing_happened(callback)

    def test_delivery_errors_from_the_mime_builder_pass_through_unchanged(self):
        callback = MagicMock()

        with self.assertRaises(PermanentEmailDeliveryError) as caught:
            make_provider().send(simple_message(to=()), before_provider_call=callback)

        self.assertEqual(str(caught.exception), "Email has no recipients.")
        self.assertIsNone(caught.exception.__cause__)
        self.assert_nothing_happened(callback)

    def test_every_delivery_error_class_is_re_raised_as_the_same_object(self):
        for error in (
            PermanentEmailDeliveryError("permanent"),
            TransientEmailDeliveryError("transient"),
            UncertainEmailDeliveryError("uncertain"),
        ):
            with self.subTest(type(error).__name__):
                callback = MagicMock()

                with patch.object(graph_provider, "build_mime_message", side_effect=error):
                    with self.assertRaises(type(error)) as caught:
                        make_provider().send(simple_message(), before_provider_call=callback)

                self.assertIs(caught.exception, error)
                self.assert_nothing_happened(callback)

    def test_value_and_unicode_errors_become_one_generic_permanent_error(self):
        messages = {
            "linefeed in the subject": simple_message(subject="Hello\nBcc: evil@example.com"),
            "unencodable character in the body": simple_message(text_body="broken \ud800 surrogate"),
        }
        for label, message in messages.items():
            with self.subTest(label):
                callback = MagicMock()

                with self.assertRaises(PermanentEmailDeliveryError) as caught:
                    make_provider().send(message, before_provider_call=callback)

                self.assertEqual(str(caught.exception), "The email could not be composed for Microsoft Graph.")
                self.assertIsInstance(caught.exception.__cause__, ValueError)
                self.assert_nothing_happened(callback)

    def test_a_unicode_error_raised_by_the_builder_is_also_generic_and_permanent(self):
        original = UnicodeError("builder failed on secret-looking text")

        with patch.object(graph_provider, "build_mime_message", side_effect=original):
            with self.assertRaises(PermanentEmailDeliveryError) as caught:
                make_provider().send(simple_message())

        self.assertNotIn("secret-looking", str(caught.exception))
        self.assertIs(caught.exception.__cause__, original)
        self.assertEqual(self.fake.requests, [])
