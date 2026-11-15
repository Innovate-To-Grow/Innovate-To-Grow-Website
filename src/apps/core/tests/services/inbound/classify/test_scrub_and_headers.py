"""Scrubbing personal sign-in links out of inbound mail, and reading hostile headers within bounds."""

from datetime import UTC, datetime
from email.message import EmailMessage

from django.test import SimpleTestCase

from apps.core.services.email.inbound import LINK_PLACEHOLDER, is_sensitive_url, scrub_links, scrub_subject
from apps.core.services.email.inbound import headers as mime

TOKEN = "fake-test-token-0000000000"  # a synthetic value: only its position matters


class ScrubTests(SimpleTestCase):
    def test_every_personal_link_shape_is_removed(self):
        links = (
            f"https://i2g.ucmerced.edu/login-link#token={TOKEN}",
            f"https://i2g.ucmerced.edu/login-link/?token={TOKEN}",
            f"https://i2g.ucmerced.edu/magic-login?token={TOKEN}",
            f"https://i2g.ucmerced.edu/impersonate-login#token={TOKEN}",
            "https://api.i2g.ucmerced.edu/mail/unsubscribe/fake-unsubscribe-0000/",
            "https://api.i2g.ucmerced.edu/mail/resubscribe/fake-unsubscribe-0000/",
            "https://i2g.ucmerced.edu/unsubscribe-login?member=1",
            f"https://partner.example/reset?user=1&reset_token={TOKEN}",
        )
        for link in links:
            with self.subTest(link):
                self.assertTrue(is_sensitive_url(link))
                self.assertEqual(scrub_links(f"Use {link} today."), f"Use {LINK_PLACEHOLDER} today.")

    def test_a_link_wrapped_by_a_safe_links_service_is_removed(self):
        wrapped = (
            "https://nam12.safelinks.protection.outlook.com/?url=https%3A%2F%2Fi2g.ucmerced.edu%2Flogin-link"
            f"%23token%3D{TOKEN}&data=05%7C02"
        )

        self.assertEqual(scrub_links(wrapped), LINK_PLACEHOLDER)

    def test_html_attributes_and_escaped_ampersands_are_scrubbed(self):
        html = f'<a href="https://site.example/x?a=1&amp;token={TOKEN}">sign in</a>'

        self.assertEqual(scrub_links(html), f'<a href="{LINK_PLACEHOLDER}">sign in</a>')

    def test_a_link_encoded_too_many_times_is_left_alone(self):
        nested = "https://example.org/?u=" + "%25" * 6 + "41"

        self.assertFalse(is_sensitive_url(nested))

    def test_ordinary_links_and_text_stay(self):
        text = "See https://i2g.ucmerced.edu/events/ and www.example.org/unsubscribe/short now."

        self.assertEqual(scrub_links(text), text)
        self.assertFalse(is_sensitive_url("https://example.org/page?tokenize=1"))

    def test_long_token_runs_are_redacted(self):
        self.assertEqual(scrub_links("code " + "A" * 80 + " end"), "code [redacted] end")

    def test_long_ordinary_links_stay_whole_and_only_token_segments_go(self):
        # The run rule used to span a link's host and path, so a shared document's address became "https:[redacted]".
        links = (
            "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdefgh/edit",
            "https://ucmerced.box.com/s/abcdefghijklmnopqrstuvwxyz0123456789abcdefghijkl",
            "https://www.ucmerced.edu/academics/schools/engineering/innovate-to-grow-program-overview-2026",
        )
        for link in links:
            with self.subTest(link):
                self.assertEqual(scrub_links(f"See {link} today."), f"See {link} today.")
                self.assertEqual(scrub_links(f'<a href="{link}">{link}</a>'), f'<a href="{link}">{link}</a>')
        opaque = "https://files.example/get?id=" + "Q" * 70 + "&x=1"

        self.assertEqual(scrub_links(opaque), "https://files.example/get?id=[redacted]&x=1")
        self.assertEqual(scrub_links("key " + "a/b" * 30 + " after"), "key [redacted] after")

    def test_subjects_are_single_line_scrubbed_and_bounded(self):
        subject = scrub_subject(
            f"Re:\r\n your link https://i2g.ucmerced.edu/login-link#token={TOKEN}\x00" + " word" * 100
        )

        self.assertTrue(subject.startswith(f"Re: your link {LINK_PLACEHOLDER}"))
        self.assertEqual(len(subject), 255)
        self.assertNotIn("\x00", subject)
        self.assertEqual(scrub_subject(None), "")


class HeaderTests(SimpleTestCase):
    def message(self, **headers) -> bytes:
        mail = EmailMessage()
        for name, value in headers.items():
            mail[name.replace("_", "-")] = value
        mail.set_content("body")
        return mail.as_bytes()

    def test_header_values_are_cut_before_they_are_read(self):
        raw = (
            b"From: a@example.org\r\nSubject: " + b"S" * 5000 + b"\r\nReferences: " + b"<a@b> " * 5000 + b"\r\n\r\nbody"
        )
        headers = mime.header_map(mime.parse(raw))

        self.assertEqual(len(headers["subject"][0]), mime.LIMIT)
        self.assertEqual(len(headers["references"][0]), 16 * mime.LIMIT)
        self.assertEqual(len(mime.message_ids(mime.joined(headers, "references"))), 1)

    def test_nul_characters_are_dropped_from_header_values(self):
        # PostgreSQL text cannot hold NUL: a Message-ID carrying one would make the message impossible to store.
        raw = b"From: a@example.org\r\nMessage-ID: <m1\x00x@example.org>\r\nReferences: <r\x001@x> <r2@x>\r\n\r\nbody"

        headers = mime.header_map(mime.parse(raw))

        self.assertEqual(headers["message-id"], ["<m1x@example.org>"])
        self.assertEqual(mime.message_ids(mime.joined(headers, "references")), ["<r1@x>", "<r2@x>"])

    def test_at_most_max_headers_are_kept(self):
        raw = b"".join(b"X-Filler-%d: v\r\n" % index for index in range(500)) + b"\r\nbody"

        headers = mime.header_map(mime.parse(raw))

        self.assertEqual(sum(len(values) for values in headers.values()), mime.MAX_HEADERS)

    def test_addresses_decode_names_and_drop_invalid_entries(self):
        value = "=?utf-8?q?Jos=C3=A9?= <JOSE@Example.ORG>, not-an-address, b@example.org"

        self.assertEqual(mime.addresses(value), [("José", "jose@example.org"), ("", "b@example.org")])
        self.assertEqual(mime.addresses(value, limit=1), [("José", "jose@example.org")])

    def test_message_ids_keep_the_most_recent(self):
        chain = " ".join(f"<id{index}@example.org>" for index in range(60))

        found = mime.message_ids(chain)

        self.assertEqual(len(found), mime.MAX_MESSAGE_IDS)
        self.assertEqual(found[-1], "<id59@example.org>")

    def test_decoding_and_dates_survive_garbage(self):
        self.assertEqual(mime.decoded("=?bogus-charset?q?abc?="), "=?bogus-charset?q?abc?=")
        self.assertEqual(mime.date("Wed, 11 Nov 2026 10:00:00 +0000"), datetime(2026, 11, 11, 10, 0, tzinfo=UTC))
        self.assertEqual(mime.date("Wed, 11 Nov 2026 10:00:00"), datetime(2026, 11, 11, 10, 0, tzinfo=UTC))
        self.assertIsNone(mime.date("not a date"))
        self.assertIsNone(mime.date(""))

    def test_content_type_and_its_parameters(self):
        raw = b'Content-Type: multipart/report; report-type=delivery-status; boundary="b"\r\n\r\n--b--\r\n'

        content_type, params = mime.content_type(mime.parse(raw))

        self.assertEqual((content_type, params["report-type"]), ("multipart/report", "delivery-status"))
        self.assertEqual(mime.first({}, "subject"), "")
