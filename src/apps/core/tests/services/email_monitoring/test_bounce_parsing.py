"""Reading bounce reports (``bounces.dsn``) and classifying each recipient (``bounces.classify``)."""

import time
from datetime import UTC, datetime

from django.test import SimpleTestCase

from apps.core.models import EmailBounce
from apps.core.services.email.bounces.classify import classify, reason
from apps.core.services.email.bounces.dsn import parse_report, strip_report_prefix

from .ndr_samples import ORIGINAL_ID, exchange_ndr, gmail_dsn, old_style_bounce, personal_email

Classification = EmailBounce.Classification


class ParseReportTests(SimpleTestCase):
    def test_an_exchange_ndr_gives_recipient_status_diagnostic_and_the_original_ids(self):
        report = parse_report(exchange_ndr())

        self.assertTrue(report.structured)
        self.assertEqual(report.reporting_mta, "SJ0PR01MB0001.namprd01.prod.outlook.com")
        self.assertEqual(report.arrival_at, datetime(2026, 11, 9, 18, 0, 2, tzinfo=UTC))
        self.assertEqual(report.report_message_id, "<ndr-1@SJ0PR01MB0001.namprd01.prod.outlook.com>")
        self.assertEqual(report.original_message_id, ORIGINAL_ID)
        self.assertEqual(report.original_subject, "Your login code - Innovate to Grow")
        (row,) = report.recipients
        self.assertEqual((row.recipient, row.action, row.status), ("nobody@example.com", "failed", "5.1.10"))
        self.assertIn("RESOLVER.ADR.RecipientNotFound", row.diagnostic)
        self.assertNotIn("smtp;", row.diagnostic)
        self.assertEqual(row.remote_mta, "mx.example.com")

    def test_a_gmail_dsn_with_the_whole_original_attached_yields_only_its_headers(self):
        report = parse_report(gmail_dsn())

        (row,) = report.recipients
        self.assertEqual((row.recipient, row.status), ("gone@gmail.com", "5.1.1"))
        self.assertEqual(row.last_attempt_at, datetime(2026, 11, 9, 18, 1, 3, tzinfo=UTC))
        self.assertEqual((report.original_message_id, report.original_subject), (ORIGINAL_ID, "Campaign news"))
        self.assertNotIn("must never be stored", repr(report))

    def test_every_recipient_of_a_multi_recipient_report_is_read(self):
        report = parse_report(exchange_ndr(extra_recipient=("second@example.com", "5.2.2", "failed")))

        self.assertEqual(
            [(r.recipient, r.status) for r in report.recipients],
            [
                ("nobody@example.com", "5.1.10"),
                ("second@example.com", "5.2.2"),
            ],
        )

    def test_the_original_recipient_is_preferred_and_the_final_one_used_without_it(self):
        self.assertEqual(
            parse_report(exchange_ndr(original_recipient=False)).recipients[0].recipient, "nobody@example.com"
        )

    def test_a_delay_notice_is_read_as_delayed(self):
        (row,) = parse_report(exchange_ndr(status="4.4.7", action="delayed")).recipients

        self.assertEqual((row.action, row.status), ("delayed", "4.4.7"))

    def test_an_old_style_bounce_uses_x_failed_recipients_and_its_status_line(self):
        report = parse_report(old_style_bounce())

        self.assertFalse(report.structured)
        (row,) = report.recipients
        self.assertEqual((row.recipient, row.action, row.status), ("gone@example.org", "failed", "5.1.1"))
        self.assertEqual(row.diagnostic, "550 5.1.1 User unknown")

    def test_a_persons_email_that_mentions_a_bounce_is_not_a_report(self):
        self.assertIsNone(parse_report(personal_email()))

    def test_a_report_cut_off_after_its_status_part_still_parses(self):
        raw = exchange_ndr()
        cut = raw[: raw.index(b"Content-Type: text/rfc822-headers")]

        report = parse_report(cut)

        self.assertEqual(report.recipients[0].status, "5.1.10")
        self.assertEqual(report.original_message_id, ORIGINAL_ID)  # from In-Reply-To
        self.assertEqual(report.original_subject, "Your login code - Innovate to Grow")  # from the report subject

    def test_a_hostile_header_is_cut_before_it_is_parsed(self):
        # A quoted-string From header the modern policy parses in super-linear time (16K characters: >1 s before).
        raw = ("From: " + '""' * 100_000 + " <postmaster@x.net>\r\nSubject: Undeliverable: x\r\n\r\nbody\r\n").encode()

        started = time.perf_counter()
        report = parse_report(raw)

        self.assertLess(time.perf_counter() - started, 0.5)
        self.assertIsNone(report)  # the cut header names no report sender

    def test_a_report_names_at_most_the_recipient_cap(self):
        blocks = [(f"extra{index}@example.com", "5.1.1", "failed") for index in range(120)]
        raw = exchange_ndr(extra_recipient=blocks[0])
        many = raw.replace(
            b"--ndr\r\nContent-Type: text/rfc822-headers",
            b"".join(
                b"Final-Recipient: rfc822;%s\r\nAction: failed\r\nStatus: 5.1.1\r\n\r\n" % address.encode()
                for address, _status, _action in blocks
            )
            + b"--ndr\r\nContent-Type: text/rfc822-headers",
        )

        self.assertEqual(len(parse_report(many, max_recipients=50).recipients), 50)
        self.assertEqual(len(parse_report(old_style_bounce(), max_recipients=1).recipients), 1)

    def test_encoded_words_are_decoded_and_undecodable_bytes_are_stored_safely(self):
        raw = exchange_ndr(subject="=?utf-8?q?Caf=C3=A9_night?=").replace(
            b"Arrival-Date", b"X-Junk: \xff\xfe\r\nArrival-Date"
        )

        report = parse_report(raw)

        self.assertEqual(report.original_subject, "Café night")
        self.assertEqual(report.recipients[0].status, "5.1.10")

    def test_report_subject_prefixes_are_stripped(self):
        for subject, original in (
            ("Undeliverable: Hello", "Hello"),
            ("Delivery Status Notification (Failure): Hi", "Hi"),
            ("Returned mail: see transcript", "see transcript"),
            ("Plain subject", "Plain subject"),
        ):
            with self.subTest(subject=subject):
                self.assertEqual(strip_report_prefix(subject), original)


class ClassifyTests(SimpleTestCase):
    """The coarse classification and ``is_permanent`` ("the address itself will not work"); the categories behind them
    are tested in ``test_bounce_categories``."""

    def test_hard_bounces(self):
        for status in ("5.1.1", "5.1.10", "5.1.2", "5.2.1", "5.4.1", "5.4.4"):
            with self.subTest(status=status):
                verdict = classify("failed", status)
                self.assertEqual((verdict.classification, verdict.is_permanent), (Classification.HARD, True))

    def test_a_bare_generic_code_is_unknown_not_hard(self):
        verdict = classify("failed", "5.0.0")

        self.assertEqual((verdict.classification, verdict.is_permanent), (Classification.UNKNOWN, None))

    def test_soft_bounces_never_say_the_address_will_not_work(self):
        for status in ("5.2.2", "5.3.4", "5.4.300", "4.4.7", "4.2.2", "5.6.1"):
            with self.subTest(status=status):
                verdict = classify("failed", status)
                self.assertEqual((verdict.classification, verdict.is_permanent), (Classification.SOFT, False))

    def test_policy_rejections(self):
        for status in ("5.7.1", "5.7.509", "5.7.606"):
            with self.subTest(status=status):
                verdict = classify("failed", status)
                self.assertEqual((verdict.classification, verdict.is_permanent), (Classification.REJECTED, False))

    def test_a_delay_is_never_a_failure(self):
        verdict = classify("delayed", "4.4.7")

        self.assertEqual((verdict.classification, verdict.is_permanent), (Classification.DELAYED, False))

    def test_no_status_code_is_unknown(self):
        verdict = classify("failed", "")

        self.assertEqual((verdict.classification, verdict.is_permanent), (Classification.UNKNOWN, None))

    def test_a_report_that_the_message_went_through_is_ignored(self):
        for action, status in (("delivered", "2.0.0"), ("relayed", "2.0.0"), ("expanded", "2.0.0"), ("", "2.1.5")):
            with self.subTest(action=action):
                self.assertIsNone(classify(action, status))

    def test_reasons_name_known_codes_and_fall_back_to_the_status_subject(self):
        self.assertEqual(reason("5.1.10"), "Recipient not found")
        self.assertEqual(reason("5.1.99"), "Recipient address problem")
        self.assertEqual(reason("4.7.0"), "Temporary: rejected by security or policy")
        self.assertEqual(reason("bad"), "")
