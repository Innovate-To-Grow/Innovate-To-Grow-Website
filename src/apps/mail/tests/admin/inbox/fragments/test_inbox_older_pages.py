"""The fragment view's "Load older": ``?older=1&cursor=`` returns only the next page of rows and its own footer."""

from apps.mail.services.inbox import InboxBusy, InboxError, InboxListing, paging
from apps.mail.tests.admin.inbox.universal.helpers import GRAPH, IMAP, UniversalInboxViewCase, summary

OLDER_TEMPLATE = "admin/mail/inbox/list/_inbox_older.html"


class FirstPageFooterTests(UniversalInboxViewCase):
    def test_the_first_page_carries_the_cursor_of_the_next(self):
        cursor = {GRAPH.key: "s1", IMAP.key: "u1"}
        self.list_all.return_value = InboxListing(messages=[summary("g1", GRAPH)], cursor=cursor)

        response = self.fragment()

        self.assertContains(response, f'data-inbox-older="{paging.encode(cursor)}"')
        self.assertContains(response, "Load older")
        self.assertContains(response, 'data-inbox-pages="1"')

    def test_a_busy_first_page_names_it_once(self):
        self.list_all.return_value = InboxListing(
            messages=[summary("g1", GRAPH)], busy=["i2g@gmail.com: Gmail is busy."]
        )

        self.assertContains(self.fragment(), "Gmail is busy.", count=1)

    def test_nothing_older_says_so(self):
        self.list_all.return_value = InboxListing(messages=[summary("g1", GRAPH)], cursor={GRAPH.key: "x"})

        response = self.fragment()

        self.assertNotContains(response, "data-inbox-older=")
        self.assertContains(response, "No older messages.")

    def test_one_account_advances_its_own_cursor(self):
        self.list_one.return_value = [summary("9", IMAP), summary("5", IMAP)]

        response = self.fragment("?account=imap:7&limit=15")

        self.assertNotContains(response, "data-inbox-older=")
        self.assertContains(response, "No older messages.")
        self.list_one.return_value = [summary(str(uid), IMAP) for uid in range(30, 15, -1)]
        self.assertContains(self.fragment("?account=imap:7&limit=15"), paging.encode({IMAP.key: "u16"}))


class OlderPageTests(UniversalInboxViewCase):
    def older(self, cursor, query=""):
        return self.fragment(f"?older=1&cursor={paging.encode(cursor)}{query}")

    def test_an_older_page_is_rows_and_a_footer_only(self):
        cursor = {GRAPH.key: "s30", IMAP.key: "u40"}
        self.list_all.return_value = InboxListing(messages=[summary("g9", GRAPH)], cursor={GRAPH.key: "s31"})

        response = self.older(cursor)

        self.assertTemplateUsed(response, OLDER_TEMPLATE)
        self.list_all.assert_called_once_with(limit=30, force_refresh=False, folder="INBOX", cursor=cursor)
        self.assertContains(response, "data-inbox-older-page")
        self.assertContains(response, 'data-uid="graph:i2g@contoso.com|g9"')
        self.assertContains(response, paging.encode({GRAPH.key: "s31"}))
        self.assertNotContains(response, "i2g-mail-toolbar")

    def test_a_malformed_cursor_starts_over(self):
        self.fragment("?older=1&cursor=not-a-cursor")

        self.list_all.assert_called_once_with(limit=30, force_refresh=False, folder="INBOX", cursor={})

    def test_a_cursor_is_ignored_on_a_full_list(self):
        self.fragment(f"?cursor={paging.encode({IMAP.key: 'u3'})}")

        self.list_all.assert_called_once_with(limit=30, force_refresh=False, folder="INBOX", cursor={})

    def test_one_account_pages_from_its_position(self):
        self.list_one.return_value = [summary("3", IMAP)]

        response = self.older({IMAP.key: "u4"}, "&account=imap:7")

        self.list_one.assert_called_once_with(
            limit=30, force_refresh=False, folder="INBOX", account="imap:7", cursor={IMAP.key: "u4"}
        )
        self.assertContains(response, 'data-uid="imap:7|3"')
        self.assertContains(response, "No older messages.")

    def test_an_exhausted_account_is_not_advanced(self):
        self.list_one.return_value = []

        response = self.older({IMAP.key: "x"}, "&account=imap:7")

        self.assertContains(response, "No older messages.")

    def test_a_failed_page_offers_retry_with_the_same_cursor(self):
        cursor = {GRAPH.key: "s30"}
        self.list_all.side_effect = InboxError("Graph down")

        response = self.older(cursor)

        self.assertContains(response, 'role="alert"')
        self.assertContains(response, f'data-inbox-older="{paging.encode(cursor)}"')
        self.assertContains(response, "Retry")

    def test_a_held_back_page_shows_what_it_last_read(self):
        busy = InboxBusy("Gmail is busy; try again in about 30 seconds.", 30)
        busy.stale = [summary("2", IMAP)]
        self.list_one.side_effect = busy

        response = self.older({IMAP.key: "u4"}, "&account=imap:7")

        self.assertContains(response, "Gmail is busy")
        self.assertContains(response, 'data-uid="imap:7|2"')
        self.assertContains(response, paging.encode({IMAP.key: "u4"}))
