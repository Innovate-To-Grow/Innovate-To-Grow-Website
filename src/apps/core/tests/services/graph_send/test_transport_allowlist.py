"""The Graph transport's request allowlist: only the token request, ``sendMail`` and three read-only GETs.

OIT reportedly granted ``Mail.ReadWrite`` (beyond the approved ``Mail.Read``), so the token itself would let a
request create, change or delete mail. The allowlist makes "the site never modifies mail" a property of the code:
anything else is refused before a connection is opened.
"""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.core.services.email import PermanentEmailDeliveryError
from apps.core.services.email.graph import access_check, auth, transport
from apps.core.services.email.graph.mailbox import GraphMailboxReader, GraphReadError
from apps.core.services.email.graph.provider import GraphProvider
from apps.core.tests.graph_helpers import CLIENT_ID, TENANT_ID, create_graph_config, make_test_credential
from apps.core.tests.services.test_email_graph_transport import CONNECTION, make_connection

GRAPH = transport.GRAPH_HOST
AUTHORITY = transport.AUTHORITY_HOST
MAILBOX = "i2g@ucmerced.edu"
USER = f"/v1.0/users/{MAILBOX}"
MESSAGE_ID = "AAMkAGI2THVSAAA="
ALLOWED = [
    ("POST", AUTHORITY, f"/{TENANT_ID}/oauth2/v2.0/token"),
    ("POST", AUTHORITY, "/contoso.onmicrosoft.com/oauth2/v2.0/token"),
    ("POST", GRAPH, f"{USER}/sendMail"),
    ("POST", GRAPH, "/v1.0/users/72f988bf-86f1-41af-91ab-2d7cd011db47/sendMail"),
    ("POST", GRAPH, "/v1.0/users/first.last%2Btag@ucmerced.edu/sendMail"),
    ("GET", GRAPH, f"{USER}/mailFolders/inbox/messages?$top=30&$select=id,subject&$orderby=receivedDateTime%20desc"),
    ("GET", GRAPH, f"{USER}/mailFolders/sentitems/messages?$top=1"),
    ("GET", GRAPH, f"{USER}/mailFolders/inbox?$select=id"),
    ("GET", GRAPH, f"{USER}/mailFolders/inbox"),
    ("GET", GRAPH, f"{USER}/messages/{MESSAGE_ID}/$value"),
]
REFUSED = {
    "update a message (mark read)": ("PATCH", GRAPH, f"{USER}/messages/{MESSAGE_ID}"),
    "replace a message": ("PUT", GRAPH, f"{USER}/messages/{MESSAGE_ID}"),
    "delete a message": ("DELETE", GRAPH, f"{USER}/messages/{MESSAGE_ID}"),
    "create a draft": ("POST", GRAPH, f"{USER}/messages"),
    "create a draft in a folder": ("POST", GRAPH, f"{USER}/mailFolders/inbox/messages"),
    "send a draft": ("POST", GRAPH, f"{USER}/messages/{MESSAGE_ID}/send"),
    "reply through Graph": ("POST", GRAPH, f"{USER}/messages/{MESSAGE_ID}/createReply"),
    "move a message": ("POST", GRAPH, f"{USER}/messages/{MESSAGE_ID}/move"),
    "copy a message": ("POST", GRAPH, f"{USER}/messages/{MESSAGE_ID}/copy"),
    "create a folder": ("POST", GRAPH, f"{USER}/mailFolders"),
    "create an inbox rule": ("POST", GRAPH, f"{USER}/mailFolders/inbox/messageRules"),
    "read another folder": ("GET", GRAPH, f"{USER}/mailFolders/deleteditems/messages"),
    "read message metadata": ("GET", GRAPH, f"{USER}/messages/{MESSAGE_ID}"),
    "read all messages": ("GET", GRAPH, f"{USER}/messages"),
    "read attachments": ("GET", GRAPH, f"{USER}/messages/{MESSAGE_ID}/attachments"),
    "list users": ("GET", GRAPH, "/v1.0/users"),
    "signed-in user": ("GET", GRAPH, "/v1.0/me/sendMail"),
    "beta endpoint": ("POST", GRAPH, "/beta/users/i2g@ucmerced.edu/sendMail"),
    "GET on sendMail": ("GET", GRAPH, f"{USER}/sendMail"),
    "query on sendMail": ("POST", GRAPH, f"{USER}/sendMail?x=1"),
    "trailing slash": ("POST", GRAPH, f"{USER}/sendMail/"),
    "fragment": ("GET", GRAPH, f"{USER}/mailFolders/inbox#x"),
    "dot segment as mailbox": ("POST", GRAPH, "/v1.0/users/../sendMail"),
    "encoded dot segment": ("POST", GRAPH, "/v1.0/users/%2e%2e/sendMail"),
    "encoded slash in the mailbox": ("POST", GRAPH, "/v1.0/users/a%2Fmessages%2Fx/sendMail"),
    "encoded backslash in the mailbox": ("POST", GRAPH, "/v1.0/users/a%5Cb/sendMail"),
    "sendMail on the identity host": ("POST", AUTHORITY, f"{USER}/sendMail"),
    "token request on the Graph host": ("POST", GRAPH, f"/{TENANT_ID}/oauth2/v2.0/token"),
    "GET on the token endpoint": ("GET", AUTHORITY, f"/{TENANT_ID}/oauth2/v2.0/token"),
    "v1 token endpoint": ("POST", AUTHORITY, f"/{TENANT_ID}/oauth2/token"),
    "another host": ("POST", "graph.microsoft.com.evil.example", f"{USER}/sendMail"),
    "lower-case method": ("post", GRAPH, f"{USER}/sendMail"),
    "space in the path": ("GET", GRAPH, f"{USER}/mailFolders/inbox/messages?$top=1 HTTP/1.1"),
}


class AllowlistTests(SimpleTestCase):
    def test_the_requests_the_site_makes_are_allowed(self):
        for method, host, path in ALLOWED:
            with self.subTest(method=method, path=path):
                self.assertTrue(transport.is_allowed(method, host, path))

    def test_everything_else_is_refused(self):
        for label, (method, host, path) in REFUSED.items():
            with self.subTest(label):
                self.assertFalse(transport.is_allowed(method, host, path))

    @patch(CONNECTION)
    def test_a_refused_request_never_opens_a_connection(self, connection_class):
        calls = {
            "post": lambda path: transport.post(GRAPH, path, b"{}", {}, timeout=5),
            "get": lambda path: transport.get(GRAPH, path, {}, timeout=5, max_bytes=10),
        }
        for name, call in calls.items():
            for path in (f"{USER}/messages", f"{USER}/messages/{MESSAGE_ID}/move"):
                with self.subTest(name, path=path), self.assertRaises(transport.RequestNotAllowed) as caught:
                    call(path)
                self.assertIsInstance(caught.exception, PermanentEmailDeliveryError)
                self.assertEqual(str(caught.exception), "The site does not make this Microsoft Graph request.")
        connection_class.assert_not_called()

    def test_only_get_and_post_are_ever_allowed(self):
        self.assertEqual({method for method, _host, _pattern in transport.ALLOWED_REQUESTS}, {"GET", "POST"})


@patch(CONNECTION)
class CodePathsStayOnTheAllowlistTests(TestCase):
    """Each place that talks to Microsoft builds a request the allowlist admits (a connection is opened)."""

    def connection(self, connection_class, *, status, body=b""):
        connection = make_connection(status=status, body=body)
        connection_class.return_value = connection
        return connection

    def requested(self, connection):
        method, path = connection.request.call_args.args
        return method, path

    def test_token_request(self, connection_class):
        connection = self.connection(connection_class, status=400)

        auth.post_token_request(TENANT_ID, CLIENT_ID, "assertion", timeout=5)

        self.assertEqual(self.requested(connection), ("POST", f"/{TENANT_ID}/oauth2/v2.0/token"))

    def test_send_mail_mime_and_json(self, connection_class):
        connection = self.connection(connection_class, status=202)
        provider = GraphProvider(
            credential=make_test_credential(), mailbox="i2g@ucmerced.edu", from_email="i2g@ucmerced.edu"
        )

        for content_type in ("text/plain", "application/json"):
            with self.subTest(content_type):
                provider._post("token", b"body", content_type)
                self.assertEqual(self.requested(connection), ("POST", f"{USER}/sendMail"))

    def test_mailbox_reader_list_and_raw_message(self, connection_class):
        reader = GraphMailboxReader(create_graph_config(scope=(MAILBOX,)), MAILBOX)

        with patch.object(auth, "get_access_token", return_value="token"):
            connection = self.connection(connection_class, status=200, body=b'{"value": []}')
            for folder, name in (("INBOX", "inbox"), ("SENT", "sentitems")):
                with self.subTest(folder):
                    reader.list_messages(folder, 5)
                    method, path = self.requested(connection)
                    self.assertEqual(method, "GET")
                    self.assertTrue(path.startswith(f"{USER}/mailFolders/{name}/messages?"))
            connection = self.connection(connection_class, status=200, body=b"Subject: x\r\n\r\nbody")
            reader.fetch_mime(MESSAGE_ID)
            self.assertEqual(self.requested(connection), ("GET", f"{USER}/messages/{MESSAGE_ID}/$value"))

    def test_access_check_probes(self, connection_class):
        connection = self.connection(connection_class, status=403)

        access_check._probe_read("token", "other@ucmerced.edu", expect_allowed=False, timeout=5)
        self.assertEqual(
            self.requested(connection), ("GET", "/v1.0/users/other@ucmerced.edu/mailFolders/inbox?$select=id")
        )
        access_check._probe_send("token", "other@ucmerced.edu", "i2g@ucmerced.edu", expect_allowed=False, timeout=5)
        self.assertEqual(self.requested(connection), ("POST", "/v1.0/users/other@ucmerced.edu/sendMail"))


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
        with patch.object(transport, "is_allowed", return_value=False), patch(CONNECTION) as connection_class:
            read = access_check._probe_read("token", "a@ucmerced.edu", expect_allowed=True, timeout=5)
            send = access_check._probe_send("token", "a@ucmerced.edu", "a@ucmerced.edu", expect_allowed=True, timeout=5)

        for result in (read, send):
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
