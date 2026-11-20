"""Sign-in links in the shapes the fourth and fifth live checks found slipping through, and saved messages past the
limit:

- a text file, a note, a reply or a message (its text, HTML and forwards) loses only the link: each link of a row is
  judged on its own, so the Docs link in the previous cell, the CSV cell after an unquoted link, a "|", "?" or ":"
  after it, a calendar's "\\n" escape and the ")." closing a sentence stay; a line of thousands of links is read in
  one pass (it once failed the import);
- a UTF-16 file sent without a byte order mark is read, and written back, in the byte order it was written in;
- a calendar or contact file (``.ics``, ``.vcf``) folds long lines, so a link folded across lines is found whole
  (and one without a link is stored byte for byte);
- an HTML link is judged as the browser reads it: a tab or line break inside the href still makes it a sign-in link;
- a saved message past the limit of five, or one that cannot be read, is counted and named on the message's card
  (the original is in Outlook) instead of vanishing, and the message is not said to be cut off."""

import codecs

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.core.services.email.inbound import LINK_PLACEHOLDER as REMOVED

from ...models import HelpdeskSettings
from ...services.ingest.reading import attachments as files
from ...services.ingest.reading.message import MAX_ATTACHED_MESSAGES, ParsedAttachment
from ...services.ingest.reading.parse import parse
from ...services.ingest.reading.sanitize import sanitize_html
from ...services.tickets import scrub_sign_in_links
from .. import corpus
from ..helpers import helpdesk_staff, receive
from ..service.intake.test_signin_links_in_files import DOC, LINK, SAVED, TOKEN, mail_with


def folded(line: str) -> str:
    """``line`` folded as RFC 5545 asks: at most 75 octets, each continuation starting with a space."""
    parts = [line[:75], *(line[index : index + 74] for index in range(75, len(line), 74))]
    return "\r\n ".join(parts)


class TextFileTests(SimpleTestCase):
    def test_only_the_link_goes_the_text_after_it_stays(self):
        data = f"Pat Doe,pat@example.org,{LINK},team A\r\nJo (see {LINK}).,jo@example.org,,last\r\n".encode()

        stored = files.scrub_text_file(data)

        self.assertEqual(
            stored, f"Pat Doe,pat@example.org,{REMOVED},team A\r\nJo (see {REMOVED}).,jo@example.org,,last\r\n".encode()
        )

    def test_each_link_of_a_row_is_judged_on_its_own(self):
        rows = (
            f"Pat Doe,{DOC},{LINK},team A\r\nLee Kim,www.example.org/info,{LINK},team B\r\nPat|{LINK}|team A|R101\r\n"
            f"Did you get {LINK}?\r\n{LINK}:\r\nfirst: {LINK}\\nAgenda: posters at 9\\, demos at 10.\r\n"
        )
        note = f"Doc then link: {DOC},{LINK},team B. Did you get {LINK}? Pat|{LINK}|team C"

        self.assertEqual(files.scrub_text_file(rows.encode()), rows.replace(LINK, REMOVED).encode())
        self.assertEqual(scrub_sign_in_links(note), note.replace(LINK, REMOVED))  # notes and replies alike

    def test_a_line_of_thousands_of_links_is_stored_with_each_one_replaced(self):
        # Once per link the old rule called itself: past about 1,000 links the import failed (RecursionError) for good.
        data = (",".join([LINK] * 2000) + "\r\n").encode()

        (row,) = files.prepare(
            [ParsedAttachment("links.csv", "text/csv", data=data, size=len(data))], HelpdeskSettings(), truncated=False
        )

        self.assertEqual(row["content"], (",".join([REMOVED] * 2000) + "\r\n").encode())

    def test_utf16_without_a_byte_order_mark_is_read_and_written_in_the_order_it_was_sent(self):
        # RFC 2781 says big-endian, yet either order is sent; Python's "utf-16" read both as little-endian (so a
        # big-endian file kept its link) and wrote a mark back.
        text = f"Sign in: {LINK}\r\nThanks, Quinn\r\n"
        for codec in ("utf-16-be", "utf-16-le"):
            with self.subTest(codec):
                self.assertEqual(
                    files.scrub_text_file(text.encode(codec), "utf-16"), text.replace(LINK, REMOVED).encode(codec)
                )
                plain = "No link here, only text.\r\n".encode(codec)
                self.assertEqual(files.scrub_text_file(plain, "utf-16"), plain)
        marked = codecs.BOM_UTF16_LE + text.encode("utf-16-le")
        expected = codecs.BOM_UTF16_LE + text.replace(LINK, REMOVED).encode("utf-16-le")
        self.assertEqual(files.scrub_text_file(marked, "utf-16"), expected)  # a file with a mark keeps it

    def test_a_link_folded_across_calendar_lines_is_found_whole(self):
        # Folded inside "login-link": neither line holds anything that looks like a sign-in link.
        head, tail = LINK.split("login-link")
        invite = (
            f"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDESCRIPTION:Sign in at {head}log\r\n in-link{tail}\r\nEND:VEVENT\r\n"
        )
        plain = f"BEGIN:VCALENDAR\r\n{folded('DESCRIPTION:' + 'Showcase on Friday at ten. ' * 6)}\r\nEND:VCALENDAR\r\n"
        self.assertNotIn(LINK, invite)
        self.assertIn(TOKEN, invite)

        row = files.prepare(
            [
                ParsedAttachment("invite.ics", "text/calendar", data=invite.encode(), size=len(invite)),
                ParsedAttachment("plain.ics", "application/octet-stream", data=plain.encode(), size=len(plain)),
            ],
            HelpdeskSettings(),
            truncated=False,
        )

        self.assertNotIn(TOKEN.encode(), row[0]["content"])
        self.assertIn(f"DESCRIPTION:Sign in at {REMOVED}".encode(), row[0]["content"])
        self.assertEqual(row[1]["content"], plain.encode())


class LinkTests(SimpleTestCase):
    def test_a_tab_or_line_break_inside_an_href_still_makes_it_a_sign_in_link(self):
        broken = LINK.replace("login-link", "login-li&#10;nk").replace("token", "to&#9;ken")

        cleaned = sanitize_html(f'<p><a href="{broken}">split</a></p>', max_chars=10000)[0]

        self.assertEqual(cleaned, f"<p>split {REMOVED}</p>")


class MessageTextTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_the_words_after_a_link_stay_in_the_message_its_html_and_a_forward(self):
        # Inbound mail is scrubbed by the same rule as files and notes: core's scrub_links once took the whole run.
        words = f"I tried the link (see {LINK}). It did not work.\nRoster line: Pat Doe,{DOC},{LINK},team A"

        ticket = receive(corpus.message(text=words, html=f"<p>Plain (see {LINK}). Next sentence.</p>"))
        forwarded = receive(corpus.forwarded(inner_text=words))

        message = ticket.messages.get()
        self.assertEqual(message.body_text.strip(), words.replace(LINK, REMOVED))
        self.assertEqual(message.body_html, f"<p>Plain (see {REMOVED}). Next sentence.</p>")
        (attached,) = forwarded.messages.get().attached_messages
        self.assertEqual(attached["text"].strip(), words.replace(LINK, REMOVED))


class SavedMessageTests(TestCase):
    def test_saved_messages_past_the_limit_or_unreadable_are_counted_not_taken_for_a_cut(self):
        many = [(f"booth-{number}.eml", SAVED, "application/octet-stream", {}) for number in range(7)]
        within = many[:MAX_ATTACHED_MESSAGES]

        past, empty, fine = (
            parse(mail_with(*many)),
            parse(mail_with(("empty.eml", b"", "application/octet-stream", {}))),
            parse(mail_with(*within)),
        )

        self.assertEqual(
            (len(past.attached_messages), past.attached_dropped, past.incomplete), (MAX_ATTACHED_MESSAGES, 2, False)
        )
        self.assertEqual((empty.attached_dropped, empty.incomplete), (1, False))
        self.assertEqual((len(fine.attached_messages), fine.attached_dropped), (MAX_ATTACHED_MESSAGES, 0))

    def test_the_card_names_the_saved_messages_left_out(self):
        cache.clear()
        self.client.force_login(helpdesk_staff())
        many = [(f"booth-{number}.eml", SAVED, "application/octet-stream", {}) for number in range(7)]
        ticket = receive(mail_with(*many))

        page = self.client.get(reverse("admin:helpdesk_ticket_change", args=[ticket.pk]))

        self.assertContains(page, "2 more attached messages are not shown (more than five, or not readable)")
        self.assertNotContains(page, "This message was cut off here")
