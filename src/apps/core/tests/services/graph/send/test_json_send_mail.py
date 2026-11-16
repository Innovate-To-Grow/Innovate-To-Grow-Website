"""Credential mail through Microsoft Graph: JSON ``sendMail`` with ``saveToSentItems`` false, no Sent Items copy.

A MIME ``sendMail`` request always files a copy in the sender mailbox's Sent Items, where anyone who can read the
folder could use a sign-in code or login link. Messages marked ``keep_sent_copy=False`` therefore go as JSON.
"""

import json

from django.test import SimpleTestCase

from apps.core.tests.services.graph.provider.test_email_graph import (
    ACCESS_TOKEN,
    MAILBOX,
    GraphFixtureMixin,
    make_provider,
    sent_mime,
    simple_message,
    ticket_message,
)

JSON_LOGGER = "apps.core.services.email.graph.json_message"


def credential_message(**overrides):
    values = {"keep_sent_copy": False, "html_body": "<p>Your code is 482913</p>", "text_body": None}
    return simple_message(**{**values, **overrides})


class _JsonSendMailRequestCase(GraphFixtureMixin, SimpleTestCase):
    def send(self, message, **provider_overrides):
        return make_provider(**provider_overrides).send(message)

    def sent_json(self):
        return json.loads(self.fake.send_requests[-1].body)


class JsonSendMailRequestTests(_JsonSendMailRequestCase):
    def test_credential_mail_is_json_with_save_to_sent_items_false(self):
        result = self.send(credential_message())

        request = self.fake.send_requests[0]
        self.assertEqual(request.path, f"/v1.0/users/{MAILBOX}/sendMail")
        self.assertEqual(request.headers["Content-Type"], "application/json")
        self.assertEqual(request.headers["Authorization"], f"Bearer {ACCESS_TOKEN}")
        body = json.loads(request.body)
        self.assertEqual(set(body), {"message", "saveToSentItems"})
        self.assertIs(body["saveToSentItems"], False)
        self.assertEqual(
            body["message"],
            {
                "subject": "Subject",
                "body": {"contentType": "HTML", "content": "<p>Your code is 482913</p>"},
                "from": {"emailAddress": {"address": MAILBOX, "name": "Innovate to Grow"}},
                "toRecipients": [{"emailAddress": {"address": "to@example.com"}}],
            },
        )
        # Graph assigns no id and the JSON form sets no Message-ID header, so none is reported.
        self.assertEqual((result.provider, result.message_id, result.accepted), ("graph", "", True))

    def test_ordinary_mail_still_goes_as_mime_and_keeps_its_headers(self):
        self.send(ticket_message())

        request = self.fake.send_requests[0]
        self.assertEqual(request.headers["Content-Type"], "text/plain")
        self.assertEqual(sent_mime(request)["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")

    def test_text_only_mail_is_sent_as_text(self):
        self.send(credential_message(html_body=None, text_body="Code: 482913"))

        self.assertEqual(self.sent_json()["message"]["body"], {"contentType": "Text", "content": "Code: 482913"})

    def test_the_html_body_wins_when_both_bodies_exist(self):
        self.send(credential_message(text_body="plain", html_body="<p>html</p>"))

        self.assertEqual(self.sent_json()["message"]["body"], {"contentType": "HTML", "content": "<p>html</p>"})

    def test_maps_every_recipient_list_and_reply_to(self):
        message = credential_message(
            to=("a@example.com", "Bea Example <b@example.com>"),
            cc=("c@example.com",),
            bcc=("d@example.com",),
            reply_to=("replies@example.com",),
        )

        self.send(message)

        sent = self.sent_json()["message"]
        self.assertEqual(
            sent["toRecipients"],
            [
                {"emailAddress": {"address": "a@example.com"}},
                {"emailAddress": {"address": "b@example.com", "name": "Bea Example"}},
            ],
        )
        self.assertEqual(sent["ccRecipients"], [{"emailAddress": {"address": "c@example.com"}}])
        # Unlike MIME, the JSON form has its own Bcc list, so Bcc is delivered rather than refused.
        self.assertEqual(sent["bccRecipients"], [{"emailAddress": {"address": "d@example.com"}}])
        self.assertEqual(sent["replyTo"], [{"emailAddress": {"address": "replies@example.com"}}])

    def test_a_blank_from_name_is_left_out(self):
        self.send(credential_message(), from_name="")

        self.assertEqual(self.sent_json()["message"]["from"], {"emailAddress": {"address": MAILBOX}})
