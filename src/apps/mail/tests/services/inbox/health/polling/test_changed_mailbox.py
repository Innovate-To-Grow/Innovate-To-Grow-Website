"""``inbox.polling``: an account whose mailbox changed never reuses the old mailbox's snapshot."""

from django.utils import timezone

from apps.mail.models import InboxAccountState
from apps.mail.services.inbox.reading.connection import InboxBusy
from apps.mail.services.inbox.reading.listing import list_inbox_messages
from apps.mail.tests.services.inbox.health.polling.helpers import (
    FakeMailbox,
    PollCase,
    Status,
)


class ChangedMailboxTests(PollCase):
    """An IMAP account's key is its row (``imap:<pk>``), so when staff point the row at another mailbox (a new Gmail
    username) the key stays the same. The old mailbox's snapshot must never be listed under the new address, and the
    incremental poll must not reuse its summaries for uids the two mailboxes share (IMAP uids restart at 1 in every
    mailbox): ``health.states_for`` ignores a state recorded for another address."""

    def setUp(self):
        super().setUp()
        InboxAccountState.objects.create(
            account_key=self.imap_key,
            address="i2g@gmail.com",
            status=Status.OK,
            snapshot_at=timezone.now(),
            messages=[{"uid": "1", "subject": "Old mailbox private subject", "is_seen": True}],
        )
        self.gmail.gmail_username = "someone-else@gmail.com"
        self.gmail.save()

    def test_the_new_mailbox_is_not_listed_with_the_old_ones_mail(self):
        self.use_mailbox(FakeMailbox([1]))

        subjects = [m["subject"] for m in list_inbox_messages(limit=30, account=self.imap_key)]

        self.assertNotIn("Old mailbox private subject", subjects)

    def test_the_poll_does_not_reuse_the_old_mailboxs_summaries(self):
        self.use_mailbox(FakeMailbox([1]))

        self.poll()

        self.assertEqual([m["subject"] for m in self.row(self.imap_key).messages], ["Mail 1"])
        self.assertEqual(self.row(self.imap_key).address, "someone-else@gmail.com")

    # ``record_ok`` without messages and ``record_failure`` write the new address; they must drop the old snapshot.
    def test_a_smaller_live_read_does_not_adopt_the_old_snapshot(self):
        self.use_mailbox(FakeMailbox([1]))
        # A list smaller than the snapshot records the connection only (``record_ok`` without messages) ...
        list_inbox_messages(limit=30, account=self.imap_key)

        # ... after which a list the snapshot could serve must still not show the old mailbox's mail.
        subjects = [m["subject"] for m in list_inbox_messages(limit=15, account=self.imap_key)]

        self.assertNotIn("Old mailbox private subject", subjects)

    def test_a_held_back_read_does_not_fall_back_to_the_old_snapshot(self):
        self.open_inbox.side_effect = InboxBusy("Gmail is busy; try again in about 30 seconds.", 30)

        with self.assertRaises(InboxBusy) as raised:
            list_inbox_messages(limit=30, account=self.imap_key)

        self.assertIsNone(raised.exception.stale)
