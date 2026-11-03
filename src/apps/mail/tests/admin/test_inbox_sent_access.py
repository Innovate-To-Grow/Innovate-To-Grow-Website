"""Sent mail of the sending mailbox (the Graph mailbox, or the Gmail account the site sends as) is readable by staff
granted the Mail app, like a superuser: the Sent folder, the site's own messages in any folder, and replies to them.

Every inbox view needs the Mail app first, so ``helpers.sent_mail_restricted`` only matters to someone without it,
for whom Sent mail stays hidden. The site's tagged credential mail is still left out of Sent for every reader
(``services/inbox/test_gmail_credential_copies`` and ``apps.mail.services.inbox.messages``).
"""

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.admin.inbox import helpers

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
    """A superuser, a Mail-only staff member, a Core-only staff member, and the Graph inbox backend switched on."""

    def setUp(self):
        cache.clear()
        self.superuser = make_superuser()
        self.mail_staff = make_admin(apps=["mail"], email="mail-only@example.com")
        self.core_staff = make_admin(apps=["core"], email="core-only@example.com")
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

    def test_mail_staff_get_the_sent_folder_like_a_superuser(self):
        for user in (self.superuser, self.mail_staff):
            with self.subTest(superuser=user.is_superuser):
                self.list_messages.reset_mock()

                response = self.fragment(user)

                self.list_messages.assert_called_once_with(limit=30, force_refresh=True, folder="SENT")
                self.assertContains(response, 'data-inbox-folder="SENT"')
        self.graph_active.assert_not_called()

    def test_mail_staff_see_own_mail_in_full(self):
        self.list_messages.return_value = [_summary(subject=f"Your code {CODE}", from_own_mailbox=True)]

        response = self.fragment(self.mail_staff)

        self.assertContains(response, f"Your code {CODE}")
        self.assertNotContains(response, helpers.OWN_MAIL_SUBJECT)

    def test_staff_without_the_mail_app_cannot_open_the_inbox(self):
        response = self.fragment(self.core_staff)

        self.assertEqual(response.status_code, 403)
        self.list_messages.assert_not_called()


class SentMailRestrictedTests(SentAccessTestCase):
    """The rule itself, for someone who reaches it without the Mail app (every inbox view refuses them first)."""

    def test_only_a_reader_without_the_mail_app_is_restricted(self):
        self.assertFalse(helpers.sent_mail_restricted(self.superuser))
        self.assertFalse(helpers.sent_mail_restricted(self.mail_staff))
        self.assertTrue(helpers.sent_mail_restricted(self.core_staff))
        self.assertTrue(helpers.sent_mail_restricted(AnonymousUser()))

    def test_an_unresolvable_backend_keeps_sent_mail_hidden_from_them(self):
        self.graph_active.side_effect = RuntimeError("boom")

        with self.assertLogs("apps.mail.admin.inbox", "ERROR"):
            self.assertTrue(helpers.sent_mail_restricted(self.core_staff))
        self.assertFalse(helpers.sent_mail_restricted(self.mail_staff))

    def test_their_list_keeps_rows_of_own_mail_without_subject_or_opening_text(self):
        own = _summary(uid="OWN", subject=f"Your code {CODE}", snippet=f"Sign in: {CODE}", from_own_mailbox=True)
        inbound = _summary(uid="IN", subject="Question about Demo Day")

        hidden, shown = helpers.hide_own_mail([own, inbound])

        self.assertEqual((hidden["subject"], hidden["snippet"]), (helpers.OWN_MAIL_SUBJECT, ""))
        self.assertEqual(shown["subject"], "Question about Demo Day")


class SentMessageDetailTests(SentAccessTestCase):
    def get(self, user, name, folder):
        self.client.force_login(user)
        return self.client.get(self.url(name, _message()["uid"], folder=folder))

    def test_mail_staff_open_sent_mail_like_a_superuser(self):
        for user in (self.superuser, self.mail_staff):
            for folder in ("SENT", "INBOX"):
                for name in ("mail_inbox_detail", "mail_inbox_detail_fragment"):
                    with self.subTest(name, folder=folder, superuser=user.is_superuser):
                        self.assertContains(self.get(user, name, folder), "Spring newsletter")

    def test_staff_without_the_mail_app_cannot_open_it_and_nothing_is_fetched(self):
        for name in ("mail_inbox_detail", "mail_inbox_detail_fragment"):
            with self.subTest(name):
                response = self.get(self.core_staff, name, "SENT")

                self.assertEqual(response.status_code, 403)
                self.assertNotContains(response, CODE, status_code=403)
        self.fetch.assert_not_called()


class SentMessageReplyTests(SentAccessTestCase):
    """A reply quotes the original, so replying to Sent mail needs what opening it needs: the Mail app."""

    def test_mail_staff_reply_to_sent_mail_like_a_superuser(self):
        for user in (self.superuser, self.mail_staff):
            with self.subTest(superuser=user.is_superuser):
                self.send_reply.reset_mock()
                self.client.force_login(user)
                uid = _message()["uid"]

                fragment = self.client.get(self.url("mail_inbox_reply_fragment", uid))
                answer = self.client.post(
                    self.url("mail_inbox_reply_fragment", uid), {"reply_body": "Hi", "to_email": "member@example.com"}
                )

                self.assertContains(fragment, "Re: Spring newsletter")
                self.assertEqual(answer.json(), {"ok": True, "message": "Reply sent to member@example.com."})
                self.send_reply.assert_called_once()

    def test_staff_without_the_mail_app_cannot_reply(self):
        self.client.force_login(self.core_staff)
        uid = _message()["uid"]
        post = {"reply_body": "Forwarding this", "to_email": "outsider@example.com"}

        self.assertEqual(self.client.get(self.url("mail_inbox_reply", uid)).status_code, 403)
        self.assertEqual(self.client.post(self.url("mail_inbox_reply_fragment", uid), post).status_code, 403)
        self.send_reply.assert_not_called()
