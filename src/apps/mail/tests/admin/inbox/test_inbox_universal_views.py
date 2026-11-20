"""The universal inbox in the admin views: ``?account=`` picks one mailbox (default: all of them), and a reply names
the address it is sent From (``sender``)."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_superuser
from apps.mail.services.inbox import ALL_ACCOUNTS, InboxAccount, InboxBusy, InboxListing, SendIdentity

SERVICES = "apps.mail.admin.inbox.services"
GRAPH = InboxAccount("graph:i2g@contoso.com", "graph", "i2g@contoso.com", "Microsoft Graph")
IMAP = InboxAccount("imap:7", "imap", "i2g@gmail.com", "imap.gmail.com", 7)
DEFAULT = SendIdentity("default", "notify@ucmerced.edu", "ses", "Notification Delivery · AWS SES")
IMAP_SENDER = SendIdentity("imap:7", "i2g@gmail.com", "gmail_smtp", "SMTP · smtp.gmail.com", 7)


def summary(uid, account, **overrides):
    return {
        "uid": uid,
        "from_name": "Pat Lee",
        "from_email": "pat@example.com",
        "to": [],
        "subject": f"Subject {uid}",
        "snippet": "Body",
        "date": "2026-01-01",
        "timestamp": 1.0,
        "is_seen": True,
        "from_own_mailbox": False,
        "account": account.key,
        "account_address": account.address,
    } | overrides


def detail(account=IMAP, **overrides):
    return {
        "uid": "42",
        "from_name": "Pat Lee",
        "from_email": "pat@example.com",
        "to": [{"name": "", "email": account.address}],
        "subject": "Question",
        "date": "2026-01-01",
        "html": "<p>Hello team.</p>",
        "text": "Hello team.",
        "message_id": "<msg@example.com>",
        "references": "",
        "reply_to": "",
        "return_path": "",
        "authentication_results": "",
        "from_own_mailbox": False,
        "account": account.key,
        "account_address": account.address,
    } | overrides


class UniversalInboxViewCase(TestCase):
    accounts = [GRAPH, IMAP]

    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.hidden = []
        self.connectable = self.patch("connectable_accounts", side_effect=self.connectable_accounts)
        self.list_one = self.patch("list_inbox_messages", return_value=[summary("1", IMAP)])
        self.list_all = self.patch(
            "list_all_inbox_messages", return_value=InboxListing(messages=[summary("g1", GRAPH), summary("1", IMAP)])
        )

    def connectable_accounts(self, *, retry=False):
        hidden = [] if retry else list(self.hidden)
        return [item for item in self.accounts if item not in hidden], hidden

    def patch(self, name, **kwargs):
        patcher = patch(f"{SERVICES}.{name}", **kwargs)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def fragment(self, query=""):
        return self.client.get(reverse("admin:mail_inbox_fragment") + query)


class InboxListAccountTests(UniversalInboxViewCase):
    def test_all_accounts_by_default(self):
        response = self.fragment()

        self.list_all.assert_called_once_with(limit=30, force_refresh=False, folder="INBOX")
        self.list_one.assert_not_called()
        self.assertContains(response, "data-inbox-account")
        self.assertContains(response, f'<option value="{ALL_ACCOUNTS}" selected>All accounts</option>', html=False)
        self.assertContains(response, "All accounts (2)")
        # Each row opens the message in the account it was read from.
        self.assertContains(response, 'data-uid="graph:i2g@contoso.com|g1"')
        self.assertContains(response, 'data-uid="imap:7|1"')
        self.assertContains(response, "?folder=INBOX&amp;account=graph%3Ai2g%40contoso.com")
        self.assertContains(response, "?folder=INBOX&amp;account=imap%3A7")
        self.assertContains(response, "data-inbox-row-account")

    def test_an_account_key_lists_that_account_only(self):
        response = self.fragment("?account=imap:7&refresh=1")

        self.list_one.assert_called_once_with(limit=30, force_refresh=True, folder="INBOX", account="imap:7")
        self.list_all.assert_not_called()
        self.assertContains(response, '<option value="imap:7" selected>', html=False)
        self.assertNotContains(response, f'<option value="{ALL_ACCOUNTS}" selected>', html=False)
        self.assertContains(response, "imap.gmail.com")
        self.assertNotContains(response, "data-inbox-row-account")

    def test_an_unknown_account_key_falls_back_to_all(self):
        for key in ("bogus", "imap:999", "graph:other@contoso.com"):
            with self.subTest(key=key):
                self.list_all.reset_mock()

                response = self.fragment(f"?account={key}")

                self.list_all.assert_called_once()
                self.assertContains(response, f'<option value="{ALL_ACCOUNTS}" selected>', html=False)
        self.list_one.assert_not_called()

    def test_busy_accounts_are_named(self):
        self.list_all.return_value = InboxListing(
            messages=[summary("g1", GRAPH)],
            busy=["i2g@gmail.com: Gmail is busy; try again in about 30 seconds."],
            showing_stale=True,
        )

        response = self.fragment()

        self.assertContains(response, "Gmail is busy; try again in about 30 seconds.")
        self.assertContains(response, "Subject g1")
        self.assertNotContains(response, "data-inbox-hidden")

    def test_an_account_that_could_not_connect_is_not_offered_and_is_named(self):
        self.hidden = [IMAP]

        response = self.fragment()

        self.list_all.assert_called_once_with(limit=30, force_refresh=False, folder="INBOX")
        self.assertEqual(self.connectable.call_args_list[0].kwargs, {"retry": False})
        self.assertContains(response, "data-inbox-hidden")
        self.assertContains(
            response,
            "Not shown because they could not connect: i2g@gmail.com. "
            "They are tried again automatically, or now with Refresh.",
        )
        # One account left: no account choice, and the header names it.
        self.assertNotContains(response, 'aria-label="Inbox account"')
        self.assertNotContains(response, '<option value="imap:7"', html=False)
        self.assertContains(response, "i2g@contoso.com")

    def test_a_hidden_account_key_falls_back_to_all(self):
        self.hidden = [IMAP]

        response = self.fragment("?account=imap:7")

        self.list_one.assert_not_called()
        self.list_all.assert_called_once_with(limit=30, force_refresh=False, folder="INBOX")
        self.assertContains(response, "data-inbox-hidden")

    def test_refresh_retries_every_account(self):
        self.hidden = [IMAP]

        response = self.fragment("?account=imap:7&refresh=1")

        self.assertEqual(self.connectable.call_args_list[0].kwargs, {"retry": True})
        self.list_one.assert_called_once_with(limit=30, force_refresh=True, folder="INBOX", account="imap:7")
        # After the read the account is named again if it still could not connect.
        self.assertEqual(self.connectable.call_args_list[-1].kwargs, {"retry": False})
        self.assertContains(response, "data-inbox-hidden")

    def test_the_shell_names_its_auto_refresh_interval(self):
        response = self.fragment()

        self.assertContains(response, 'data-inbox-auto-refresh="60"')

    def test_a_held_back_single_account_shows_its_last_list(self):
        busy = InboxBusy("Gmail is busy; try again in about 30 seconds.", 30)
        busy.stale = [summary("old", IMAP, subject="Stale subject")]
        self.list_one.side_effect = busy

        response = self.fragment("?account=imap:7")

        self.assertContains(response, "Gmail is busy; try again in about 30 seconds.")
        self.assertContains(response, "Stale subject")
        self.assertNotContains(response, "data-inbox-hidden")

    def test_an_account_listing_failure_still_renders(self):
        self.connectable.side_effect = RuntimeError("boom")

        with self.assertLogs("apps.mail.admin.inbox", "ERROR"):
            response = self.fragment("?account=imap:7")

        self.assertEqual(response.status_code, 200)
        self.list_all.assert_called_once()
        self.assertContains(response, "Not configured")


class SingleAccountListTests(UniversalInboxViewCase):
    accounts = [IMAP]

    def test_one_account_offers_no_account_choice(self):
        self.list_all.return_value = InboxListing(messages=[summary("1", IMAP)])

        response = self.fragment()

        self.assertNotContains(response, 'aria-label="Inbox account"')
        self.assertNotContains(response, "data-inbox-row-account")
        self.assertContains(response, "i2g@gmail.com")


class InboxDetailAccountTests(UniversalInboxViewCase):
    def setUp(self):
        super().setUp()
        self.fetch = self.patch("fetch_inbox_message", return_value=detail())

    def test_the_detail_page_reads_the_named_account_and_replies_in_it(self):
        response = self.client.get(reverse("admin:mail_inbox_detail", args=["42"]) + "?account=imap:7")

        self.fetch.assert_called_once_with("42", folder="INBOX", account="imap:7")
        self.assertContains(response, reverse("admin:mail_inbox_reply", args=["42"]) + "?account=imap%3A7")

    def test_the_detail_fragment_reads_the_named_account_and_replies_in_it(self):
        response = self.client.get(
            reverse("admin:mail_inbox_detail_fragment", args=["42"]) + "?folder=INBOX&account=imap:7"
        )

        self.fetch.assert_called_once_with("42", folder="INBOX", account="imap:7")
        self.assertContains(response, reverse("admin:mail_inbox_reply_fragment", args=["42"]) + "?account=imap%3A7")

    def test_without_an_account_the_urls_carry_none(self):
        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.fetch.assert_called_once_with("42", folder="INBOX", account="")
        self.assertNotContains(response, "?account=")


class ReplySenderViewTests(UniversalInboxViewCase):
    def setUp(self):
        super().setUp()
        self.fetch = self.patch("fetch_inbox_message", return_value=detail())
        self.identities = self.patch("send_identities", return_value=[DEFAULT, IMAP_SENDER])
        self.send_reply = self.patch("send_reply", return_value="")

    def fragment_url(self, query="?account=imap:7"):
        return reverse("admin:mail_inbox_reply_fragment", args=["42"]) + query

    def test_the_form_starts_from_the_address_the_message_was_received_at(self):
        response = self.client.get(self.fragment_url())

        self.fetch.assert_called_once_with("42", account="imap:7")
        self.assertContains(response, 'name="sender"')
        self.assertContains(response, '<option value="imap:7" selected>i2g@gmail.com (SMTP · smtp.gmail.com)</option>')
        self.assertContains(response, "notify@ucmerced.edu (Notification Delivery · AWS SES)")
        self.assertNotContains(response, '<option value="default" selected>', html=False)
        self.assertContains(response, self.fragment_url().replace("imap:7", "imap%3A7"))

    def test_the_form_starts_from_notification_delivery_otherwise(self):
        self.fetch.return_value = detail(account=GRAPH)

        response = self.client.get(self.fragment_url("?account=graph:i2g@contoso.com"))

        self.assertContains(response, '<option value="default" selected>', html=False)

    def test_without_any_sender_the_form_shows_the_notification_address(self):
        self.identities.return_value = []

        response = self.client.get(self.fragment_url())

        self.assertNotContains(response, 'name="sender"')
        self.assertContains(response, "From:")

    def test_a_sender_listing_failure_is_logged_and_offers_no_choice(self):
        self.identities.side_effect = RuntimeError("boom")

        with self.assertLogs("apps.mail.admin.inbox", "ERROR"):
            response = self.client.get(self.fragment_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="sender"')

    def test_the_post_passes_the_sender_through(self):
        response = self.client.post(
            self.fragment_url(), {"reply_body": "Thanks", "to_email": "pat@example.com", "sender": "imap:7"}
        )

        self.assertEqual(response.json(), {"ok": True, "message": "Reply sent to pat@example.com."})
        self.fetch.assert_called_once_with("42", account="imap:7")
        self.assertEqual(self.send_reply.call_args.kwargs["sender"], "imap:7")

    def test_a_post_without_a_sender_uses_the_default(self):
        for data in ({}, {"sender": "  "}):
            with self.subTest(data=data):
                self.send_reply.reset_mock()

                self.client.post(self.fragment_url(), {"reply_body": "Thanks", **data})

                self.assertEqual(self.send_reply.call_args.kwargs["sender"], "default")

    def test_a_refused_sender_is_reported(self):
        self.send_reply.return_value = "That From address is not available."

        response = self.client.post(self.fragment_url(), {"reply_body": "Thanks", "sender": "imap:999"})

        self.assertEqual(response.json(), {"ok": False, "error": "That From address is not available."})

    def test_the_reply_page_offers_the_senders_and_posts_the_choice(self):
        url = reverse("admin:mail_inbox_reply", args=["42"]) + "?account=imap:7"

        page = self.client.get(url)
        sent = self.client.post(url, {"reply_body": "Thanks", "sender": "imap:7"})

        self.assertContains(page, 'id="reply-sender" name="sender"')
        self.assertContains(page, '<option value="imap:7" selected>', html=False)
        self.assertEqual(self.send_reply.call_args.kwargs["sender"], "imap:7")
        self.assertRedirects(
            sent, reverse("admin:mail_inbox_detail", args=["42"]) + "?account=imap%3A7", fetch_redirect_response=False
        )
