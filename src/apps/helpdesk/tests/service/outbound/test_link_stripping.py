"""What an outsider chose (a display name, a subject) loses anything a mail client turns into a link before the site
sends it from its own address: URLs, www. hosts, host names with a path, bare host names on common top-level domains
and IPv4 addresses. Words, version numbers, file names and ticket numbers stay."""

from django.test import SimpleTestCase, TestCase

from ....services.outbound import compose
from ...helpers.service import new_ticket

LINK = "[link removed]"


class WithoutLinksTests(SimpleTestCase):
    def test_link_like_text_is_removed(self):
        for value, expected in (
            ("confirm payroll at payroll-update.example.com now", f"confirm payroll at {LINK} now"),
            ("see https://evil.example/reset?u=staff", f"see {LINK}"),
            ("visit www.evil.example today", f"visit {LINK} today"),
            ("at evil.example/login today", f"at {LINK} today"),
            ("call 10.0.0.1:8080 or 192.168.1.20", f"call {LINK} or {LINK}"),
            ("mail pat@example.org", f"mail pat@{LINK}"),
            ("SUB.DOMAIN.CO.UK offer", f"{LINK} offer"),
        ):
            with self.subTest(value):
                self.assertEqual(compose.without_links(value), expected)

    def test_ordinary_text_stays(self):
        for value in (
            "Question about the showcase schedule",
            "Version 1.2.3 release notes",
            "Sending report.pdf and data.csv",
            "Mr.Smith, e.g. Node.js help",
            "Re: I2G-#1234 follow-up",
        ):
            with self.subTest(value):
                self.assertEqual(compose.without_links(value), value)


class FilledEmailTests(TestCase):
    def test_the_subject_and_name_lose_bare_host_names_in_notices_replies_and_fills(self):
        ticket = new_ticket(subject="Urgent: payroll-update.example.com", requester_name="Pat (pat-help.example.net)")

        self.assertEqual(
            compose.notice_subject(ticket, "Assigned to you"),
            f"[{ticket.display_number}] Assigned to you: Urgent: {LINK}",
        )
        self.assertEqual(compose.reply_subject(ticket), f"Re: Urgent: {LINK} [{ticket.display_number}]")
        self.assertEqual(compose.fill("Hello {requester_name}", ticket), f"Hello Pat ({LINK})")
