"""What an outsider chose (a display name, a subject) loses anything a mail client turns into a link before the site
sends it from its own address: URLs, www. hosts and host names with a path always; in automatic mail nobody reads
first (the acknowledgement, the notices), bare host names on common top-level domains and IPv4 addresses too. Words,
version numbers, file names and ticket numbers stay, and a staff reply's subject keeps what staff can read on the form."""

from django.test import SimpleTestCase, TestCase

from ....services.outbound import compose
from ...helpers.service import new_ticket

LINK = "[link removed]"


class WithoutLinksTests(SimpleTestCase):
    def test_links_are_always_removed(self):
        for value, expected in (
            ("see https://evil.example/reset?u=staff", f"see {LINK}"),
            ("visit www.evil.example today", f"visit {LINK} today"),
            ("at evil.example/login today", f"at {LINK} today"),
        ):
            with self.subTest(value):
                self.assertEqual(compose.without_links(value), expected)
                self.assertEqual(compose.without_links(value, strict=True), expected)

    def test_bare_host_names_and_addresses_only_in_strict_mode(self):
        for value, expected in (
            ("confirm payroll at payroll-update.example.com now", f"confirm payroll at {LINK} now"),
            ("call 10.0.0.1:8080 or 192.168.1.20", f"call {LINK} or {LINK}"),
            ("mail pat@example.org", f"mail pat@{LINK}"),
            ("SUB.DOMAIN.CO.UK offer", f"{LINK} offer"),
        ):
            with self.subTest(value):
                self.assertEqual(compose.without_links(value, strict=True), expected)
                self.assertEqual(compose.without_links(value), value)

    def test_ordinary_text_stays(self):
        for value in (
            "Question about the showcase schedule",
            "Version 1.2.3 release notes",
            "Sending report.pdf and data.csv",
            "Mr.Smith, e.g. Node.js help",
            "Re: I2G-#1234 follow-up",
        ):
            with self.subTest(value):
                self.assertEqual(compose.without_links(value, strict=True), value)


class FilledEmailTests(TestCase):
    def test_automatic_mail_loses_bare_host_names_and_a_staff_reply_keeps_them(self):
        ticket = new_ticket(subject="Urgent: payroll-update.example.com", requester_name="Pat (pat-help.example.net)")

        self.assertEqual(
            compose.notice_subject(ticket, "Assigned to you"),
            f"[{ticket.display_number}] Assigned to you: Urgent: {LINK}",
        )
        self.assertEqual(compose.reply_subject(ticket, strict=True), f"Re: Urgent: {LINK} [{ticket.display_number}]")
        self.assertEqual(compose.fill("Hello {requester_name}", ticket, strict=True), f"Hello Pat ({LINK})")
        # What staff read on the reply form and in an inserted template is sent as they read it.
        self.assertEqual(
            compose.reply_subject(ticket), f"Re: Urgent: payroll-update.example.com [{ticket.display_number}]"
        )
        self.assertEqual(compose.fill("Hello {requester_name}", ticket), "Hello Pat (pat-help.example.net)")
