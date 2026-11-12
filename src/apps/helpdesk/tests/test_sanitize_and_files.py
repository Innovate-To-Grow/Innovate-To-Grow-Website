"""Sanitizing inbound HTML (the allow-list, dropped elements, images, links, sign-in links, caps) and deciding which
attachments are stored and how they are downloaded."""

from django.test import SimpleTestCase

from apps.core.services.email.inbound import LINK_PLACEHOLDER

from ..models import HelpdeskSettings, TicketAttachment
from ..services.ingest import attachments as files
from ..services.ingest.parse import ParsedAttachment
from ..services.ingest.sanitize import frame_document, sanitize_html
from .corpus import LOGIN_LINK

LIMIT = 1024 * 1024


def clean(html: str) -> str:
    return sanitize_html(html, max_chars=LIMIT)[0]


class SanitizeTests(SimpleTestCase):
    def test_active_content_is_removed_with_what_it_holds(self):
        hostile = (
            "<script>alert(1)</script><style>p{color:red}</style><iframe src=//x></iframe><object></object>"
            "<embed><form action=//x><input name=a></form><svg><script>x</script></svg><math></math>"
            "<base href=//x><meta http-equiv=refresh><link rel=stylesheet href=//x><noscript>n</noscript><p>kept</p>"
        )

        self.assertEqual(clean(hostile), "<p>kept</p>")

    def test_event_handlers_javascript_urls_and_srcset_are_removed(self):
        html = (
            '<p onclick="steal()" onmouseover="x">a</p><a href="javascript:alert(1)">b</a>'
            '<a href="JaVaScRiPt:alert(1)">c</a><a href="data:text/html,x">d</a><p srcset="x 1x">e</p>'
        )

        cleaned = clean(html)

        for forbidden in ("onclick", "onmouseover", "javascript", "data:", "srcset"):
            self.assertNotIn(forbidden, cleaned.lower())
        self.assertIn(">b</a>", cleaned)

    def test_links_open_in_a_new_tab_without_opener_or_referrer(self):
        cleaned = clean('<a href="https://example.org/page" target="_self" rel="opener">site</a><a>bare</a>')

        self.assertEqual(
            cleaned,
            '<a rel="noopener noreferrer" target="_blank" href="https://example.org/page">site</a>'
            '<a rel="noopener noreferrer" target="_blank">bare</a>',
        )

    def test_images_become_placeholders(self):
        cleaned = clean('<p><img src="https://tracker.example/pixel.gif"><img src="cid:logo" alt="Logo"></p>')

        self.assertEqual(cleaned, "<p>[image][image: Logo]</p>")

    def test_formatting_tables_and_safe_styles_are_kept(self):
        html = (
            '<table border="1"><tr><td colspan="2" style="color: red; position: fixed; '
            'background-image: url(https://x)">cell</td></tr></table><b>bold</b><ul><li>item</li></ul>'
        )

        cleaned = clean(html)

        self.assertIn('colspan="2"', cleaned)
        self.assertIn("color: red", cleaned)
        self.assertNotIn("position", cleaned)
        self.assertNotIn("url(", cleaned)
        self.assertIn("<b>bold</b>", cleaned)
        self.assertIn("<li>item</li>", cleaned)

    def test_comments_and_documents_are_flattened(self):
        cleaned = clean("<html><head><title>t</title></head><body><!-- secret --><p>x</p></body></html>")

        self.assertEqual(cleaned, "<p>x</p>")

    def test_personal_sign_in_links_are_scrubbed(self):
        cleaned = clean(f'<p>Use <a href="{LOGIN_LINK}">{LOGIN_LINK}</a></p>')

        self.assertNotIn("token=", cleaned)
        self.assertEqual(cleaned.count(LINK_PLACEHOLDER), 2)

    def test_long_html_is_cut_and_closed_again(self):
        html = "<div>" + "<p>paragraph text</p>" * 500 + "</div>"

        cleaned, cut = sanitize_html(html, max_chars=1000)

        self.assertTrue(cut)
        self.assertLessEqual(len(cleaned), 1000)
        self.assertEqual(cleaned.count("<p>"), cleaned.count("</p>"))

    def test_empty_html_stays_empty(self):
        self.assertEqual(sanitize_html("   ", max_chars=10), ("", False))
        self.assertEqual(sanitize_html("", max_chars=10), ("", False))

    def test_the_frame_document_wraps_the_body(self):
        document = frame_document("<p>x</p>")

        self.assertTrue(document.startswith("<!doctype html>"))
        self.assertIn("<p>x</p></body></html>", document)
        self.assertNotIn("<script", document)
        self.assertNotIn("<style", document)


class AttachmentPolicyTests(SimpleTestCase):
    def setUp(self):
        self.settings = HelpdeskSettings(attachment_max_bytes=100, message_max_bytes=150)

    def item(self, filename="report.pdf", data=b"%PDF-1.7", content_type="application/pdf"):
        return ParsedAttachment(filename, content_type, data=data, size=len(data) if data else 0)

    def prepared(self, *items, truncated=False):
        return files.prepare(list(items), self.settings, truncated=truncated)

    def test_a_normal_file_is_stored_with_its_hash_and_sniffed_type(self):
        (row,) = self.prepared(self.item())

        self.assertEqual(
            (row["content"], row["detected_type"], row["blocked"], row["not_stored_reason"]),
            (b"%PDF-1.7", "application/pdf", False, ""),
        )
        self.assertEqual(len(row["sha256"]), 64)

    def test_blocked_types_keep_only_metadata(self):
        for item in (
            self.item("setup.exe", b"MZ\x90\x00"),
            self.item("invoice.pdf.js", b"var x"),
            self.item("page.HTML", b"<html>"),
            self.item("macro.docm", b"PK\x03\x04"),
            self.item("renamed.pdf", b"MZ\x90\x00"),  # an executable renamed: caught by its content
            self.item("notes.one", b"x"),
        ):
            with self.subTest(item.filename):
                (row,) = self.prepared(item)
                self.assertTrue(row["blocked"])
                self.assertIsNone(row["content"])
                self.assertIn("Blocked file type", row["not_stored_reason"])

    def test_size_caps_truncation_and_undecodable_files(self):
        too_big, fits, over_total = self.item(data=b"x" * 101), self.item(data=b"y" * 100), self.item(data=b"z" * 60)
        rows = self.prepared(too_big, fits, over_total)

        self.assertIn("larger than", rows[0]["not_stored_reason"])
        self.assertEqual(rows[1]["content"], b"y" * 100)
        self.assertIn("per-message limit", rows[2]["not_stored_reason"])
        (cut,) = self.prepared(self.item(), truncated=True)
        self.assertIn("read limit", cut["not_stored_reason"])
        (undecodable,) = self.prepared(self.item(data=None))
        self.assertIn("could not be decoded", undecodable["not_stored_reason"])

    def test_sniffing(self):
        self.assertEqual(files.sniff(b"\x89PNG\r\n\x1a\nrest"), "image/png")
        self.assertEqual(files.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8"), "image/webp")
        self.assertEqual(files.sniff(b"plain text"), "")
        self.assertEqual(files.sniff(None), "")
        self.assertEqual(
            (files.extension("a.tar.GZ"), files.extension("noext"), files.extension(".bashrc")), ("gz", "", "")
        )

    def test_download_type_and_archive_warning(self):
        settings = HelpdeskSettings()
        image = TicketAttachment(filename="photo.jpg", detected_type="image/jpeg")
        pdf = TicketAttachment(filename="report.pdf", detected_type="application/pdf")
        archive = TicketAttachment(filename="files.zip", detected_type="application/zip")
        renamed_archive = TicketAttachment(filename="files.dat", detected_type="application/zip")

        self.assertEqual(files.download_content_type(image), "image/jpeg")
        self.assertEqual(files.download_content_type(pdf), "application/octet-stream")
        self.assertTrue(files.needs_warning(archive, settings))
        self.assertTrue(files.needs_warning(renamed_archive, settings))
        self.assertFalse(files.needs_warning(pdf, settings))

    def test_extension_lists_are_parsed_leniently(self):
        self.assertEqual(HelpdeskSettings.extensions(" .EXE, js  bat"), frozenset({"exe", "js", "bat"}))
        self.assertIn("exe", HelpdeskSettings().blocked_extension_set)
        self.assertIn("zip", HelpdeskSettings().warn_extension_set)
