"""Sent mail of the Microsoft Graph mailbox is for superusers only: the Sent folder, its messages and replies.

The site's own mail lands in Sent Items (campaigns with login links, inbox replies), so Mail-app staff could read
other people's sign-in links there. A Graph message id is unique in the whole mailbox, so a message from the site's
own address counts as Sent mail whichever folder the URL names. The Gmail IMAP inbox is unchanged.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_admin, make_superuser

SERVICES = "apps.mail.admin.inbox.services"
DENIED = "Sent mail of the Microsoft Graph mailbox is shown to superusers only."
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


def _summary():
    return {
        "uid": "AAMkAGI2THVSAAA=",
        "from_name": "Innovate to Grow",
        "from_email": "i2g@ucmerced.edu",
        "to": [{"name": "", "email": "member@example.com"}],
        "subject": "Spring newsletter",
        "snippet": "Sign in",
        "date": "2026-01-01",
        "is_seen": True,
    }


class SentAccessTestCase(TestCase):
    """A superuser, a Mail-only staff member, and the Graph inbox backend switched on."""

    def setUp(self):
        cache.clear()
        self.superuser = make_superuser()
        self.mail_staff = make_admin(apps=["mail"], email="mail-only@example.com")
        EmailServiceConfig.objects.create(name="Mail", is_active=True, from_email="i2g@ucmerced.edu", from_name="I2G")
        self.graph_active = self.patch("graph_inbox_active", return_value=True)
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
        self.list_messages = self.patch("list_inbox_messages", return_value=[_summary()])

    def fragment(self, user):
        self.client.force_login(user)
        return self.client.get(self.url("mail_inbox_fragment", folder="SENT") + "&refresh=1")

    def test_mail_staff_get_the_inbox_and_no_sent_tab(self):
        response = self.fragment(self.mail_staff)

        self.assertEqual(response.status_code, 200)
        self.list_messages.assert_called_once_with(limit=30, force_refresh=True, folder="INBOX")
        self.assertContains(response, 'data-inbox-folder="INBOX"')
        self.assertNotContains(response, 'data-inbox-folder="SENT"')

    def test_superusers_keep_the_sent_folder(self):
        response = self.fragment(self.superuser)

        self.list_messages.assert_called_once_with(limit=30, force_refresh=True, folder="SENT")
        self.assertContains(response, 'data-inbox-folder="SENT"')
        self.graph_active.assert_not_called()

    def test_mail_staff_keep_the_gmail_sent_folder(self):
        self.graph_active.return_value = False

        response = self.fragment(self.mail_staff)

        self.list_messages.assert_called_once_with(limit=30, force_refresh=True, folder="SENT")
        self.assertContains(response, 'data-inbox-folder="SENT"')

    def test_an_unresolvable_backend_keeps_sent_mail_hidden(self):
        self.graph_active.side_effect = RuntimeError("boom")

        with self.assertLogs("apps.mail.admin.inbox", "ERROR"):
            response = self.fragment(self.mail_staff)

        self.list_messages.assert_called_once_with(limit=30, force_refresh=True, folder="INBOX")
        self.assertNotContains(response, 'data-inbox-folder="SENT"')


class SentMessageDetailTests(SentAccessTestCase):
    def get(self, user, name, folder):
        self.client.force_login(user)
        return self.client.get(self.url(name, _message()["uid"], folder=folder))

    def test_mail_staff_cannot_open_the_sent_folder_and_nothing_is_fetched(self):
        for name in ("mail_inbox_detail", "mail_inbox_detail_fragment"):
            with self.subTest(name):
                response = self.get(self.mail_staff, name, "SENT")

                self.assertEqual(response.status_code, 403)
                self.assertNotContains(response, CODE, status_code=403)
        self.fetch.assert_not_called()

    def test_the_preview_pane_explains_the_refusal(self):
        response = self.get(self.mail_staff, "mail_inbox_detail_fragment", "SENT")

        self.assertContains(response, DENIED, status_code=403)

    def test_a_sent_message_id_under_the_inbox_folder_is_refused_too(self):
        for name in ("mail_inbox_detail", "mail_inbox_detail_fragment"):
            with self.subTest(name):
                response = self.get(self.mail_staff, name, "INBOX")

                self.assertEqual(response.status_code, 403)
                self.assertNotContains(response, CODE, status_code=403)

    def test_mail_staff_still_open_ordinary_inbox_mail(self):
        self.fetch.return_value = _message(from_email="ada@example.com", from_own_mailbox=False)

        for name in ("mail_inbox_detail", "mail_inbox_detail_fragment"):
            with self.subTest(name):
                self.assertContains(self.get(self.mail_staff, name, "INBOX"), "Spring newsletter")

    def test_superusers_open_sent_mail(self):
        for folder in ("SENT", "INBOX"):
            for name in ("mail_inbox_detail", "mail_inbox_detail_fragment"):
                with self.subTest(name, folder=folder):
                    self.assertContains(self.get(self.superuser, name, folder), "Spring newsletter")

    def test_mail_staff_open_gmail_sent_mail(self):
        self.graph_active.return_value = False
        self.fetch.return_value = _message(from_own_mailbox=False)

        self.assertContains(self.get(self.mail_staff, "mail_inbox_detail_fragment", "SENT"), "Spring newsletter")


class SentMessageReplyTests(SentAccessTestCase):
    """A reply quotes the original, so replying to Sent mail would disclose it like opening it."""

    def test_mail_staff_cannot_load_or_send_a_reply_to_sent_mail(self):
        self.client.force_login(self.mail_staff)
        uid = _message()["uid"]
        post = {"reply_body": "Forwarding this", "to_email": "outsider@example.com"}

        self.assertEqual(self.client.get(self.url("mail_inbox_reply", uid)).status_code, 403)
        self.assertEqual(self.client.post(self.url("mail_inbox_reply", uid), post).status_code, 403)
        fragment = self.client.get(self.url("mail_inbox_reply_fragment", uid))
        self.assertContains(fragment, DENIED, status_code=403)
        self.assertNotContains(fragment, CODE, status_code=403)
        answer = self.client.post(self.url("mail_inbox_reply_fragment", uid), post)
        self.assertEqual(answer.status_code, 403)
        self.assertEqual(answer.json(), {"ok": False, "error": DENIED})
        self.send_reply.assert_not_called()

    def test_superusers_can_reply(self):
        self.client.force_login(self.superuser)
        uid = _message()["uid"]

        self.assertContains(self.client.get(self.url("mail_inbox_reply_fragment", uid)), "Re: Spring newsletter")
        answer = self.client.post(
            self.url("mail_inbox_reply_fragment", uid), {"reply_body": "Hi", "to_email": "member@example.com"}
        )
        self.assertEqual(answer.json(), {"ok": True, "message": "Reply sent to member@example.com."})
        self.send_reply.assert_called_once()

    def test_mail_staff_reply_to_ordinary_inbox_mail(self):
        self.fetch.return_value = _message(from_email="ada@example.com", from_own_mailbox=False)
        self.client.force_login(self.mail_staff)

        answer = self.client.post(
            self.url("mail_inbox_reply_fragment", _message()["uid"]),
            {"reply_body": "Hi", "to_email": "ada@example.com"},
        )

        self.assertTrue(answer.json()["ok"])
        self.send_reply.assert_called_once()
