from django.test import SimpleTestCase

from apps.core.services.email import PermanentEmailDeliveryError
from apps.core.services.email.mime import build_mime_message
from apps.core.tests.services.graph.provider.test_email_graph import (
    GraphFixtureMixin,
    make_provider,
    sent_mime,
    simple_message,
)


class MessageIdDomainTests(GraphFixtureMixin, SimpleTestCase):
    def test_graph_messages_use_the_sender_domain_in_their_message_id(self):
        result = make_provider(from_email="sender@contoso.com", mailbox="sender@contoso.com").send(simple_message())

        message_id = str(sent_mime(self.fake.send_requests[0])["Message-ID"])
        self.assertEqual(result.message_id, message_id)
        self.assertTrue(message_id.endswith("@contoso.com>"), message_id)

    def test_the_shared_builder_never_falls_back_to_the_host_name_for_a_valid_sender(self):
        mime = build_mime_message(simple_message(), from_email="i2g@g.ucmerced.edu", from_name="I2G")

        self.assertTrue(str(mime["Message-ID"]).endswith("@g.ucmerced.edu>"))

    def test_a_sender_without_a_domain_still_gets_a_message_id(self):
        self.assertTrue(build_mime_message(simple_message(), from_email="not-an-address")["Message-ID"])


class RecipientLimitTests(GraphFixtureMixin, SimpleTestCase):
    """The mailbox's recipients-per-message limit (``MicrosoftGraphProviderConfig.max_recipients_per_message``)."""

    def message(self, count):
        return simple_message(to=tuple(f"to{i}@example.com" for i in range(count)))

    def test_a_message_over_the_limit_is_refused_before_anything_is_sent(self):
        provider = make_provider(max_recipients=3)

        with self.assertRaisesMessage(
            PermanentEmailDeliveryError, "has 4 recipients; Microsoft Graph allows at most 3"
        ):
            provider.send(self.message(4))

        self.assertEqual(self.fake.requests, [])

    def test_cc_and_bcc_count_towards_the_limit(self):
        provider = make_provider(max_recipients=2)
        message = simple_message(to=("a@example.com",), cc=("b@example.com",), bcc=("c@example.com",))

        with self.assertRaises(PermanentEmailDeliveryError):
            provider.send(message)

    def test_a_message_at_the_limit_is_sent(self):
        provider = make_provider(max_recipients=3)

        result = provider.send(self.message(3))

        self.assertTrue(result.accepted)

    def test_without_a_limit_the_count_is_left_to_exchange(self):
        provider = make_provider()

        self.assertIsNone(provider.max_recipients)
        self.assertTrue(provider.send(self.message(12)).accepted)
