"""What the list and preview fragments render for the Phase 1 layout: the collapsed details panel, the quick filter,
the attachment icon, the compact security chip, "Open full page", and the assessment cached per opened message."""

from django.core.cache import cache

from apps.mail.services.inbox import InboxListing
from apps.mail.tests.admin.inbox.universal.helpers import GRAPH, IMAP, UniversalInboxViewCase, detail, summary


def assessment(risk_level, **overrides):
    return {
        "risk_level": risk_level,
        "score": {"low": 0, "medium": 4, "high": 9}[risk_level],
        "score_percent": 10,
        "reasons": [],
        "findings": [],
        "summary": "",
        "recommendation": "",
        "link_warnings": [],
    } | overrides


class ListLayoutTests(UniversalInboxViewCase):
    def test_the_details_panel_starts_collapsed(self):
        response = self.fragment()

        self.assertContains(response, 'class="i2g-mail-shell is-account-collapsed"')
        self.assertContains(response, 'aria-expanded="false"\n                aria-controls="inbox-account-panel"')
        self.assertContains(response, "Show details")

    def test_the_quick_filter_and_unread_toggle(self):
        response = self.fragment()

        self.assertContains(response, "data-inbox-filter ")
        self.assertContains(response, 'data-inbox-unread-only aria-pressed="false"')
        self.assertContains(response, "data-inbox-filter-empty hidden")
        for part in ("data-inbox-row-sender", "data-inbox-row-subject", "data-inbox-row-snippet"):
            self.assertContains(response, part)

    def test_rows_with_attachments_show_a_paperclip(self):
        self.list_all.return_value = InboxListing(
            messages=[summary("g1", GRAPH), summary("1", IMAP, has_attachments=True, is_seen=False)]
        )

        response = self.fragment()

        self.assertContains(response, "data-inbox-row-attachment", count=1)
        self.assertContains(response, 'aria-label="Has attachments"')
        self.assertContains(response, "is-unread", count=1)


class PreviewLayoutTests(UniversalInboxViewCase):
    def setUp(self):
        super().setUp()
        self.fetch = self.patch("fetch_inbox_message", return_value=detail())
        self.assess = self.patch("assess_email", return_value=assessment("low"))

    def preview(self, query="?account=imap:7"):
        return self.client.get(f"/admin/mail/inbox/42/fragment/{query}")

    def test_low_risk_is_a_closed_chip(self):
        response = self.preview()

        self.assertContains(response, '<details data-scam-analysis-panel\n         data-risk-level="low"')
        self.assertNotContains(response, 'i2g-scam-panel" open')
        self.assertNotContains(response, "data-scam-chip-warning")
        self.assertContains(response, "Low risk")

    def test_medium_risk_is_closed_with_a_warning(self):
        self.assess.return_value = assessment("medium")

        response = self.preview()

        self.assertNotContains(response, 'i2g-scam-panel" open')
        self.assertContains(response, "data-scam-chip-warning")
        self.assertContains(response, "Check the sender and links before you act on it.")

    def test_high_risk_starts_open(self):
        self.assess.return_value = assessment("high")

        response = self.preview()

        self.assertContains(response, 'i2g-scam-panel" open>')
        self.assertContains(response, "Likely a scam")

    def test_open_full_page_links_the_message_in_its_folder_and_account(self):
        for folder in ("INBOX", "SENT"):
            with self.subTest(folder=folder):
                response = self.preview(f"?folder={folder}&account=imap:7")

                self.assertContains(response, f'href="/admin/mail/inbox/42/?folder={folder}&amp;account=imap%3A7"')
                self.assertContains(response, 'target="_blank" rel="noopener" data-inbox-full-page')
        self.assertNotContains(response, "data-inbox-reply-link")  # no Reply in Sent

    def test_the_assessment_is_cached_per_opened_message(self):
        self.preview()
        self.preview()
        self.client.get("/admin/mail/inbox/42/?account=imap:7")

        self.assess.assert_called_once()
        self.fetch.return_value = detail(html="<p>Changed body</p>")
        self.preview()
        self.assertEqual(self.assess.call_count, 2)
        self.preview("?folder=SENT&account=imap:7")
        self.assertEqual(self.assess.call_count, 3)

    def test_the_cache_holds_no_message_body(self):
        self.fetch.return_value = detail(html="<p>Secret code 482913</p>")

        self.preview()

        keys = [key for key in cache._cache if "inbox:assessment:" in str(key)]  # LocMemCache in tests
        self.assertEqual(len(keys), 1)
        self.assertNotIn("482913", str(keys[0]))

    def test_the_full_page_view_links_the_panel_styles(self):
        response = self.client.get("/admin/mail/inbox/42/?account=imap:7")

        for name in ("scam-chip", "scam-risk", "scam-sections"):
            self.assertContains(response, f"mail/inbox/css/{name}.css")


class ListPageTests(UniversalInboxViewCase):
    def test_the_page_loads_the_static_scripts(self):
        response = self.client.get("/admin/mail/inbox/")

        for name in ("state", "list", "filter", "preview", "reply", "keys", "boot"):
            self.assertContains(response, f"mail/inbox/js/inbox-{name}.js")
        self.assertNotContains(response, "function fetchInbox")  # no inline inbox script any more
