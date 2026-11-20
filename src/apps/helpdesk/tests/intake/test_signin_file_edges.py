"""Sign-in links in the shapes the fourth live check found slipping through, and saved messages past the limit:

- a text file loses only the link: the CSV cell after an unquoted link, or the ")." closing a sentence, stays;
- a calendar or contact file (``.ics``, ``.vcf``) folds long lines, so a link folded across lines is found whole
  (and one without a link is stored byte for byte);
- an HTML link is judged as the browser reads it: a tab or line break inside the href still makes it a sign-in link;
- a saved message past the limit of five, or one that cannot be read, marks the message incomplete instead of
  vanishing (the original is in Outlook)."""

from django.test import SimpleTestCase

from apps.core.services.email.inbound import LINK_PLACEHOLDER as REMOVED

from ...models import HelpdeskSettings
from ...services.ingest.reading import attachments as files
from ...services.ingest.reading.message import MAX_ATTACHED_MESSAGES, ParsedAttachment
from ...services.ingest.reading.parse import parse
from ...services.ingest.reading.sanitize import sanitize_html
from ..service.intake.test_signin_links_in_files import LINK, SAVED, TOKEN, mail_with


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


class SavedMessageTests(SimpleTestCase):
    def test_saved_messages_past_the_limit_or_unreadable_mark_the_message_incomplete(self):
        many = [(f"booth-{number}.eml", SAVED, "application/octet-stream", {}) for number in range(7)]
        within = many[:MAX_ATTACHED_MESSAGES]

        past, empty, fine = (
            parse(mail_with(*many)),
            parse(mail_with(("empty.eml", b"", "application/octet-stream", {}))),
            parse(mail_with(*within)),
        )

        self.assertEqual((len(past.attached_messages), past.incomplete), (MAX_ATTACHED_MESSAGES, True))
        self.assertTrue(empty.incomplete)
        self.assertEqual((len(fine.attached_messages), fine.incomplete), (MAX_ATTACHED_MESSAGES, False))
