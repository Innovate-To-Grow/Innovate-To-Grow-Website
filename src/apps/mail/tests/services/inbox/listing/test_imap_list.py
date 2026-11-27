"""``reading.imap_list``: a page of UIDs, fetched as header + the start of the text with BODY.PEEK (never whole)."""

import base64
from datetime import UTC, datetime
from types import SimpleNamespace

from django.test import SimpleTestCase
from imap_tools.errors import MailboxFetchError

from apps.mail.services.inbox.reading import imap_list
from apps.mail.services.inbox.reading.messages import message_summary
from apps.mail.tests.services.inbox.mailbox.imap_wire import WireClient, fetch_response


def fake(uid, **overrides):
    values = {
        "uid": str(uid),
        "subject": f"Mail {uid}",
        "from_values": SimpleNamespace(name="Bob Ray", email="bob@example.com"),
        "to_values": [SimpleNamespace(name="", email="i2g@example.edu")],
        "date": datetime(2026, 10, 1 + uid % 28, 12, 0, tzinfo=UTC),
        "html": "",
        "text": f"Hello number {uid}",
        "flags": (),
        "headers": {},
    }
    return SimpleNamespace(**(values | overrides))


class ReadPageTests(SimpleTestCase):
    def setUp(self):
        self.client = WireClient([fake(uid) for uid in (3, 10, 7, 12, 5)])

    def uids(self, messages):
        return [message.uid for message in messages]

    def test_the_newest_uids_newest_first(self):
        page = imap_list.read_page(self.client, "ALL", before=None, limit=3)

        self.assertEqual(self.uids(page), ["12", "10", "7"])
        ((command, requested, parts),) = self.client.fetched
        self.assertEqual((command, requested, parts), ("FETCH", ["12", "10", "7"], imap_list.LIST_PARTS))

    def test_before_continues_below_that_uid(self):
        self.assertEqual(self.uids(imap_list.read_page(self.client, "ALL", before=7, limit=3)), ["5", "3"])
        self.assertEqual(imap_list.read_page(self.client, "ALL", before=3, limit=3), [])
        self.assertEqual(len(self.client.fetched), 1)  # nothing is fetched for an empty page

    def test_a_message_gone_before_the_fetch_is_left_out(self):
        self.client.present = {"12", "7"}

        self.assertEqual(self.uids(imap_list.read_page(self.client, "ALL", before=None, limit=3)), ["12", "7"])

    def test_the_search_criteria_and_non_numeric_answers(self):
        self.client.uids = lambda criteria: ["9", "x", "", "4"]

        self.assertEqual(self.uids(imap_list.read_page(self.client, "ALL", before=None, limit=0)), [])
        self.assertEqual(self.client.fetched, [])

    def test_the_fetch_reads_with_peek_only(self):
        self.assertIn("BODY.PEEK[HEADER]", imap_list.LIST_PARTS)
        self.assertIn(f"BODY.PEEK[TEXT]<0.{imap_list.LIST_TEXT_BYTES}>", imap_list.LIST_PARTS)
        self.assertNotRegex(imap_list.LIST_PARTS, r"BODY\[|RFC822(?!\.)")

    def test_a_failed_fetch_raises(self):
        client = SimpleNamespace(client=SimpleNamespace(uid=lambda *args: ("NO", [b"failed"])))

        with self.assertRaises(MailboxFetchError):
            imap_list.fetch_partial(client, ["1"])


class PartialMessageTests(SimpleTestCase):
    def fetch(self, message):
        (partial,) = imap_list.fetch_partial(WireClient([message]), [message.uid])
        return partial

    def test_the_summary_comes_from_the_header_and_text(self):
        summary = message_summary(self.fetch(fake(4, flags=("\\Seen",))))

        self.assertEqual((summary["uid"], summary["subject"]), ("4", "Mail 4"))
        self.assertEqual((summary["from_name"], summary["from_email"]), ("Bob Ray", "bob@example.com"))
        self.assertEqual(summary["to"], [{"name": "", "email": "i2g@example.edu"}])
        self.assertEqual(summary["snippet"], "Hello number 4")
        self.assertEqual(summary["timestamp"], datetime(2026, 10, 5, 12, 0, tzinfo=UTC).timestamp())
        self.assertEqual((summary["is_seen"], summary["has_attachments"]), (True, False))

    def test_attachments_come_from_the_bodystructure(self):
        self.assertTrue(message_summary(self.fetch(fake(4, attachments=True)))["has_attachments"])

    def test_the_plain_text_part_is_preferred_and_html_is_flattened(self):
        both = self.fetch(fake(4, html="<p>Rich <b>body</b></p>", text="Plain body"))
        html_only = self.fetch(fake(5, html="<style>p{}</style><p>Only <b>rich</b></p>", text=""))

        self.assertEqual(message_summary(both)["snippet"], "Plain body")
        self.assertEqual(message_summary(html_only)["snippet"], "Only rich")

    def test_a_long_text_is_cut_to_the_snippet(self):
        partial = self.fetch(fake(4, text="word " * 2000))

        self.assertLessEqual(len(partial.text.encode()), imap_list.LIST_TEXT_BYTES)
        self.assertTrue(message_summary(partial)["snippet"].endswith("..."))

    def test_a_cut_off_base64_part_and_an_unknown_charset_still_give_text(self):
        body = base64.b64encode(("Grüße " * 400).encode()).decode()
        header = (
            b"Subject: x\r\nContent-Type: text/plain; charset=x-unknown\r\nContent-Transfer-Encoding: base64\r\n\r\n"
        )
        data = [(b"1 (UID 8 FLAGS () BODY[HEADER] {%d}" % len(header), header)]
        data += [(b" BODY[TEXT]<0> {101}", body[:101].encode()), b")"]

        (partial,) = imap_list.fetch_partial(
            SimpleNamespace(client=SimpleNamespace(uid=lambda *a: ("OK", data))), ["8"]
        )

        self.assertTrue(partial.text.startswith("Gr"))

    def test_odd_responses(self):
        literal_structure = [
            (b'1 (UID 6 FLAGS (\\Seen) BODYSTRUCTURE ("text" "plain" NIL NIL NIL "7bit" 1 1 NIL ({9}', b'"attachment"'),
            (b' ("filename" "a")) NIL) BODY[HEADER] {12}', b"Subject: y\r\n"),
            b")",
            b"2 (FLAGS ())",  # no UID: skipped
            (b"3 (UID 9 FLAGS () BODY[HEADER] {0}", b""),
            b")",
        ]
        client = SimpleNamespace(client=SimpleNamespace(uid=lambda *a: ("OK", [b"* stray", *literal_structure])))

        first, last = imap_list.fetch_partial(client, ["6", "9"])

        self.assertEqual((first.uid, first.flags, first.subject), ("6", ("\\Seen",), "y"))
        self.assertEqual((last.uid, last.text, last.subject), ("9", "", ""))
        self.assertEqual(
            imap_list.fetch_partial(SimpleNamespace(client=SimpleNamespace(uid=lambda *a: ("OK", None))), ["1"]), []
        )

    def test_the_wire_helper_answers_in_mailbox_order(self):
        data = fetch_response([fake(1), fake(2)], ["2", "1"])

        self.assertTrue(data[0][0].startswith(b"1 (UID 1 "))

    def test_a_whole_message_says_whether_it_has_attachments(self):
        self.assertTrue(message_summary(fake(4, attachments=[object()]))["has_attachments"])
        self.assertFalse(message_summary(fake(4, attachments=[]))["has_attachments"])
        self.assertFalse(message_summary(fake(4))["has_attachments"])
