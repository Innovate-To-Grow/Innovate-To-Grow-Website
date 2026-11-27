"""The universal inbox list in the admin views: ``?account=`` picks one mailbox (default: all of them)."""

from apps.mail.services.inbox import ALL_ACCOUNTS, InboxBusy, InboxListing
from apps.mail.tests.admin.inbox.universal.helpers import (
    GRAPH,
    IMAP,
    UniversalInboxViewCase,
    summary,
)


class InboxListAccountTests(UniversalInboxViewCase):
    def test_all_accounts_by_default(self):
        response = self.fragment()

        self.list_all.assert_called_once_with(limit=30, force_refresh=False, folder="INBOX", cursor={})
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

        self.list_one.assert_called_once_with(limit=30, force_refresh=True, folder="INBOX", account="imap:7", cursor={})
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

        self.list_all.assert_called_once_with(limit=30, force_refresh=False, folder="INBOX", cursor={})
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
        self.list_all.assert_called_once_with(limit=30, force_refresh=False, folder="INBOX", cursor={})
        self.assertContains(response, "data-inbox-hidden")

    def test_refresh_retries_every_account(self):
        self.hidden = [IMAP]

        response = self.fragment("?account=imap:7&refresh=1")

        self.assertEqual(self.connectable.call_args_list[0].kwargs, {"retry": True})
        self.list_one.assert_called_once_with(limit=30, force_refresh=True, folder="INBOX", account="imap:7", cursor={})
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
