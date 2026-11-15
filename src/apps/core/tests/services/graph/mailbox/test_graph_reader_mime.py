from django.conf import settings
from django.test import TestCase

from apps.core.services.email.graph import transport
from apps.core.services.email.graph.mailbox import (
    GraphMessageNotFound,
    GraphReadError,
    is_message_id,
)
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.graph.mailbox.test_graph_mailbox_reader import (
    MAILBOX,
    MESSAGE_ID,
    GraphReaderFixtureMixin,
)
from apps.core.tests.services.graph.provider.test_email_graph import error_body, token_response


class GraphReaderMimeTests(GraphReaderFixtureMixin, TestCase):
    def test_fetches_the_raw_mime(self):
        self.get.outcome = HttpResponse(200, {}, b"Subject: hi\r\n\r\nbody")

        self.assertEqual(self.reader().fetch_mime(MESSAGE_ID), b"Subject: hi\r\n\r\nbody")

        (call,) = self.get.calls
        self.assertEqual(call["path"], f"/v1.0/users/{MAILBOX}/messages/{MESSAGE_ID}/$value")
        self.assertEqual(call["max_bytes"], settings.GRAPH_INBOX_MESSAGE_MAX_BYTES)

    def test_invalid_ids_are_refused_without_any_request(self):
        for message_id in ("", None, "../x", "a/b", "a b", "id?x=1", "a%2F", "x" * 513):
            with self.subTest(message_id):
                with self.assertRaisesMessage(GraphMessageNotFound, "Message not found."):
                    self.reader().fetch_mime(message_id)
        self.assertEqual((self.get.calls, self.fake.requests), ([], []))

    def test_truncated_mime_raises(self):
        self.get.outcome = HttpResponse(200, {}, b"x", truncated=True)

        with self.assertRaisesMessage(GraphReadError, "too large"):
            self.reader().fetch_mime(MESSAGE_ID)

    def test_is_message_id(self):
        self.assertTrue(is_message_id("AAMk-_=9"))
        self.assertFalse(is_message_id("AAMk+/"))
        self.assertFalse(is_message_id(None))


class GraphReaderErrorTests(GraphReaderFixtureMixin, TestCase):
    def fetch(self):
        return self.reader().fetch_mime(MESSAGE_ID)

    def test_401_and_403_forget_the_cached_token(self):
        for status in (401, 403):
            with self.subTest(status):
                self.script()
                self.get.outcome = [
                    HttpResponse(status, {}, error_body("ErrorAccessDenied")),
                    HttpResponse(200, {}, b""),
                ]
                with self.assertRaises(GraphReadError) as caught:
                    self.fetch()
                self.assertNotIsInstance(caught.exception, GraphMessageNotFound)
                self.fetch()
                self.assertEqual(len(self.fake.token_requests), 2)

    def test_403_names_the_mailbox_and_only_the_allow_listed_code(self):
        self.get.outcome = HttpResponse(403, {}, error_body("ErrorAccessDenied"))

        with self.assertRaises(GraphReadError) as caught:
            self.fetch()

        self.assertEqual(str(caught.exception), f"Microsoft Graph denied access to {MAILBOX} (ErrorAccessDenied).")

    def test_other_statuses_keep_the_cached_token(self):
        self.get.outcome = HttpResponse(500, {}, b"")
        for _ in range(2):
            with self.assertRaisesMessage(GraphReadError, "Microsoft Graph returned HTTP 500."):
                self.fetch()
        self.assertEqual(len(self.fake.token_requests), 1)

    def test_404_is_not_found(self):
        self.get.outcome = HttpResponse(404, {}, error_body("ErrorItemNotFound"))

        with self.assertRaisesMessage(GraphMessageNotFound, "Message not found."):
            self.fetch()

    def test_throttling_and_unavailability_are_reported_as_busy(self):
        for status in (408, 429, 503):
            with self.subTest(status):
                self.get.outcome = HttpResponse(status, {"retry-after": "5"}, b"")
                with self.assertRaisesMessage(GraphReadError, "busy; try again in a minute"):
                    self.fetch()

    def test_unreachable_graph(self):
        for error in (transport.ConnectFailed(), transport.ResponseLost()):
            with self.subTest(type(error).__name__):
                self.get.outcome = error
                with self.assertRaisesMessage(GraphReadError, "could not be reached"):
                    self.reader().list_messages("INBOX", 1)

    def test_token_failure_becomes_a_read_error_without_a_graph_request(self):
        self.script(token=HttpResponse(400, {}, b'{"error": "invalid_client"}'))

        with self.assertRaises(GraphReadError):
            self.fetch()
        self.assertEqual(self.get.calls, [])

    def test_token_is_reused_between_reads(self):
        self.script(token=token_response())
        reader = self.reader()

        reader.list_messages("INBOX", 1)
        reader.list_messages("SENT", 1)

        self.assertEqual(len(self.fake.token_requests), 1)
