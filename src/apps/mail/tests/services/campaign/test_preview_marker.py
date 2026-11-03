"""The raw-HTML storage marker: recognised however a stored body carries it, never rendered into a message."""

from django.test import SimpleTestCase

from apps.mail.services.campaign.preview import HTML_MARKER, build_email_render_context, split_html_marker

MARKER = HTML_MARKER.strip()
BODY = '<div dir="ltr"><p>Dear {{first_name}},</p></div>'


class SplitHtmlMarkerTests(SimpleTestCase):
    def test_plain_text_is_not_marked(self):
        self.assertEqual(split_html_marker("Hello\nthere"), (False, "Hello\nthere"))
        self.assertEqual(split_html_marker(""), (False, ""))
        self.assertEqual(split_html_marker(None), (False, ""))

    def test_marker_followed_by_lf_crlf_cr_space_or_nothing(self):
        for stored in (
            HTML_MARKER + BODY,
            f"{MARKER}\r\n{BODY}",
            f"{MARKER}\r{BODY}",
            f"{MARKER} {BODY}",
            f"{MARKER}  \r\n{BODY}",
            MARKER + BODY,
        ):
            with self.subTest(stored=stored):
                self.assertEqual(split_html_marker(stored), (True, BODY))

    def test_repeated_markers_are_all_removed(self):
        stored = f"{MARKER}\n{MARKER}\r\n{MARKER}\r\n{MARKER} {BODY}"

        self.assertEqual(split_html_marker(stored), (True, BODY))

    def test_marker_inside_the_body_is_content(self):
        stored = f"{BODY}\n{MARKER}\n<p>more</p>"

        self.assertEqual(split_html_marker(stored), (False, stored))


class RenderContextMarkerTests(SimpleTestCase):
    def test_marked_body_is_raw_html_without_the_marker(self):
        context = build_email_render_context(HTML_MARKER + BODY)

        self.assertEqual(context["body"], BODY)

    def test_body_with_repeated_crlf_markers_is_still_raw_html(self):
        context = build_email_render_context(f"{MARKER}\n{MARKER}\r\n{MARKER} {BODY}")

        self.assertEqual(context["body"], BODY)
        self.assertNotIn("raw-html", context["body"])

    def test_unmarked_body_is_escaped_plain_text(self):
        context = build_email_render_context("<b>not html</b>\nline two")

        self.assertEqual(context["body"], "&lt;b&gt;not html&lt;/b&gt;<br>\nline two")
