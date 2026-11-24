"""Sent mail of the sending mailbox (the Graph mailbox, or the Gmail account the site sends as) is readable by every
Admin: the Sent folder, the site's own messages in any folder, and replies to them. A member who is not an Admin
reaches none of it, and nothing is fetched or sent for them.

The site's tagged credential mail is still left out of Sent for every reader
(``services/inbox/test_gmail_credential_copies`` and ``apps.mail.services.inbox.reading.messages``).
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_admin
from apps.mail.services.inbox import InboxListing
from apps.mail.tests.admin.admin_access.refusal import assert_refused_to_member, make_member

SERVICES = "apps.mail.admin.inbox.services"
CODE = "482913"


def _message(**overrides):
    msg = {
        "uid": "AAMkAGI2THVSAAA=",
        "from_name": "Innovate to Grow",
        "from_email": "i2g@ucmerced.edu",
        "to": [{"name": "", "email": "member@example.com"}],
        "subject": "Spring newsletter",
        "date": "Mon, 01 Jan 2026 00:00:00 +0000",
        "html": f"<p>Sign in: https://i2g.example/login-link#token={CODE}</p>",
        "text": f"Sign in: https://i2g.example/login-link#token={CODE}",
        "message_id": "<msg@ucmerced.edu>",
        "references": "",
        "reply_to": "",
        "return_path": "",
        "authentication_results": "",
        "from_own_mailbox": True,
    }
    msg.update(overrides)
    return msg


def _summary(**overrides):
    return {
        "uid": "AAMkAGI2THVSAAA=",
        "from_name": "Innovate to Grow",
        "from_email": "i2g@ucmerced.edu",
        "to": [{"name": "", "email": "member@example.com"}],
        "subject": "Spring newsletter",
        "snippet": "Sign in",
        "date": "2026-01-01",
        "is_seen": True,
        "from_own_mailbox": False,
    } | overrides


class SentAccessTestCase(TestCase):
    """An Admin, a member who is not one, and an active sending configuration."""

    def setUp(self):
        cache.clear()
        self.admin_user = make_admin(email="admin@example.com")
        self.member = make_member(email="member-only@example.com")
        EmailServiceConfig.objects.create(name="Mail", is_active=True, from_email="i2g@ucmerced.edu", from_name="I2G")
        self.fetch = self.patch("fetch_inbox_message", return_value=_message())
        self.send_reply = self.patch("send_reply", return_value="")

    def patch(self, name, **kwargs):
        patcher = patch(f"{SERVICES}.{name}", **kwargs)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def url(self, name, *args, folder=None):
        url = reverse(f"admin:{name}", args=args)
        return f"{url}?folder={folder}" if folder else url


class SentFolderListTests(SentAccessTestCase):
    def setUp(self):
        super().setUp()
        # The list shows every inbox account by default (``list_all_inbox_messages``).
        self.list_messages = self.patch("list_all_inbox_messages", return_value=InboxListing(messages=[_summary()]))

    def fragment_url(self):
        return self.url("mail_inbox_fragment", folder="SENT") + "&refresh=1"

    def test_an_admin_gets_the_sent_folder(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(self.fragment_url())

        self.list_messages.assert_called_once_with(limit=30, force_refresh=True, folder="SENT")
        self.assertContains(response, 'data-inbox-folder="SENT"')

    def test_an_admin_sees_own_mail_in_full(self):
        self.list_messages.return_value = InboxListing(
            messages=[_summary(subject=f"Your code {CODE}", from_own_mailbox=True)]
        )
        self.client.force_login(self.admin_user)

        self.assertContains(self.client.get(self.fragment_url()), f"Your code {CODE}")

    def test_a_member_cannot_open_the_inbox(self):
        assert_refused_to_member(self, self.fragment_url(), self.member)

        self.list_messages.assert_not_called()


class SentMessageDetailTests(SentAccessTestCase):
    def test_an_admin_opens_sent_mail(self):
        self.client.force_login(self.admin_user)
        for folder in ("SENT", "INBOX"):
            for name in ("mail_inbox_detail", "mail_inbox_detail_fragment"):
                with self.subTest(name, folder=folder):
                    response = self.client.get(self.url(name, _message()["uid"], folder=folder))
                    self.assertContains(response, "Spring newsletter")

    def test_a_member_cannot_open_it_and_nothing_is_fetched(self):
        for name in ("mail_inbox_detail", "mail_inbox_detail_fragment"):
            with self.subTest(name):
                assert_refused_to_member(self, self.url(name, _message()["uid"], folder="SENT"), self.member)
        self.fetch.assert_not_called()


class SentMessageReplyTests(SentAccessTestCase):
    def test_an_admin_replies_to_sent_mail(self):
        self.client.force_login(self.admin_user)
        uid = _message()["uid"]

        fragment = self.client.get(self.url("mail_inbox_reply_fragment", uid))
        answer = self.client.post(
            self.url("mail_inbox_reply_fragment", uid), {"reply_body": "Hi", "to_email": "member@example.com"}
        )

        self.assertContains(fragment, "Re: Spring newsletter")
        self.assertEqual(answer.json(), {"ok": True, "message": "Reply sent to member@example.com."})
        self.send_reply.assert_called_once()

    def test_a_member_cannot_reply(self):
        uid = _message()["uid"]
        post = {"reply_body": "Forwarding this", "to_email": "outsider@example.com"}

        assert_refused_to_member(self, self.url("mail_inbox_reply", uid), self.member)
        assert_refused_to_member(self, self.url("mail_inbox_reply_fragment", uid), self.member, "post", data=post)
        self.send_reply.assert_not_called()
