from unittest.mock import patch

from django.test import TestCase

from apps.core.services.email import PermanentEmailDeliveryError
from apps.core.services.email.graph import auth, transport
from apps.core.services.email.graph.access_check.probes import Prober
from apps.core.services.email.graph.mailbox import GraphMailboxReader, GraphReadError
from apps.core.services.email.graph.provider import GraphProvider
from apps.core.tests.graph_helpers import create_graph_config, make_test_credential
from apps.core.tests.services.graph.send.test_transport_allowlist import MAILBOX, MESSAGE_ID
from apps.core.tests.services.graph.transport.test_email_graph_transport import CONNECTION


class RefusalHandlingTests(TestCase):
    """A refused request surfaces as each caller's ordinary failure, never as an unexpected exception."""

    def test_the_mailbox_reader_reports_a_read_error(self):
        reader = GraphMailboxReader(create_graph_config(scope=(MAILBOX,)), MAILBOX)

        with (
            patch.object(auth, "get_access_token", return_value="token"),
            patch.object(transport, "is_allowed", return_value=False),
            patch(CONNECTION) as connection_class,
        ):
            with self.assertRaisesMessage(GraphReadError, "The site does not make this Microsoft Graph request."):
                reader.list_messages("INBOX", 5)
            with self.assertRaisesMessage(GraphReadError, "The site does not make this Microsoft Graph request."):
                reader.fetch_mime(MESSAGE_ID)
        connection_class.assert_not_called()

    def test_access_check_probes_fail_with_the_refusal_as_note(self):
        prober = Prober("token", timeout=5)
        with patch.object(transport, "is_allowed", return_value=False), patch(CONNECTION) as connection_class:
            read = prober.folder("a@ucmerced.edu", expect_allowed=True)
            send = prober.send_mime("a@ucmerced.edu")
            deny = prober.send_json(
                "send", url_mailbox="b@ucmerced.edu", from_mailbox="b@ucmerced.edu", recipient=MAILBOX
            )

        for result in (read, send, deny):
            self.assertFalse(result.passed)
            self.assertIsNone(result.status)
            self.assertEqual(result.note, "The site does not make this Microsoft Graph request.")
        connection_class.assert_not_called()

    def test_the_provider_classifies_a_refusal_as_permanent(self):
        provider = GraphProvider(
            credential=make_test_credential(), mailbox="i2g@ucmerced.edu", from_email="i2g@ucmerced.edu"
        )

        with patch.object(transport, "is_allowed", return_value=False), patch(CONNECTION) as connection_class:
            with self.assertRaisesMessage(PermanentEmailDeliveryError, "does not make this Microsoft Graph request"):
                provider._submit("token", b"body", "text/plain", "<id@example.com>")
        connection_class.assert_not_called()
