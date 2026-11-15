"""Plain-text campaign bodies: URL auto-linking must not absorb trailing punctuation.

The campaign ``{{login_link}}`` token is exactly 64 characters. If the auto-linker swallows a
trailing ``.`` / ``)`` / ``,`` / ``!`` into the href, the emailed link carries a 65-character token
and ``/mail/login-link/`` answers "Invalid login link.".
"""

import re

from django.test import SimpleTestCase

from apps.mail.services.campaign.content.personalize import personalize
from apps.mail.services.campaign.content.preview import HTML_MARKER, _text_to_html, render_email_html

URL = "https://i2g.example/login-link#token=" + "aB3_-" * 12 + "wxyz"
ANCHOR = f'<a href="{URL}" style="color:#0f2d52;">{URL}</a>'
HREF_RE = re.compile(r'href="([^"]*)"')


def _hrefs(html):
    return HREF_RE.findall(html)


class TextToHtmlTrailingPunctuationTests(SimpleTestCase):
    def test_token_fixture_is_64_chars(self):
        self.assertEqual(len(URL.split("#token=")[1]), 64)

    def test_trailing_punctuation_is_emitted_after_the_anchor(self):
        for punctuation in [
            ".",
            ",",
            ";",
            ":",
            "!",
            "?",
            ")",
            "]",
            "}",
            "'",
            '"',
            "’",
            "”",
            "。",
            "，",
            "、",
            "；",
            "：",
            "！",
            "？",
            "…",
            "．",
            "）",
            "］",
            "｝",
            "》",
            "」",
            "』",
        ]:
            with self.subTest(punctuation=punctuation):
                html = _text_to_html(f"{URL}{punctuation}")
                self.assertEqual(_hrefs(html), [URL])
                self.assertIn(f"{ANCHOR}{_text_to_html(punctuation)}", html)

    def test_wrapped_in_parentheses(self):
        html = _text_to_html(f"({URL})")
        self.assertEqual(html, f"({ANCHOR})")
        self.assertEqual(_text_to_html(f"（{URL}）"), f"（{ANCHOR}）")

    def test_sentence_forms(self):
        for template, expected in [
            (f"Click {URL}!", f"Click {ANCHOR}!"),
            (f"Sign in at {URL}, then continue", f"Sign in at {ANCHOR}, then continue"),
            (f"Sign in ({URL}).", f"Sign in ({ANCHOR})."),
            (f"Really {URL}?!", f"Really {ANCHOR}?!"),
            (f"Trailing ellipsis {URL}...", f"Trailing ellipsis {ANCHOR}..."),
            (f"{URL}.\nNext line", f"{ANCHOR}.<br>\nNext line"),
        ]:
            with self.subTest(template=template):
                html = _text_to_html(template)
                self.assertEqual(_hrefs(html), [URL])
                self.assertEqual(html, expected)

    def test_punctuation_inside_the_url_is_kept(self):
        url = "https://i2g.example/path/file.pdf?a=1.5#frag-x"
        self.assertEqual(_text_to_html(f"{url}."), f'<a href="{url}" style="color:#0f2d52;">{url}</a>.')

    def test_balanced_brackets_inside_the_url_are_kept(self):
        url = "https://en.wikipedia.org/wiki/Innovate_(disambiguation)"
        self.assertEqual(_text_to_html(url), f'<a href="{url}" style="color:#0f2d52;">{url}</a>')
        self.assertEqual(
            _text_to_html(f"(see {url})."),
            f'(see <a href="{url}" style="color:#0f2d52;">{url}</a>).',
        )

    def test_bare_url_per_line_renders_unchanged(self):
        self.assertEqual(_text_to_html(f"Sign in:\n{URL}\nThanks"), f"Sign in:<br>\n{ANCHOR}<br>\nThanks")

    def test_angle_bracketed_url_renders_unchanged(self):
        self.assertEqual(_text_to_html(f"<{URL}>"), f"&lt;{ANCHOR}&gt;")

    def test_html_special_characters_are_still_escaped(self):
        html = _text_to_html('"<b>" & friends: ' + URL + '"')
        self.assertEqual(html, f"&quot;&lt;b&gt;&quot; &amp; friends: {ANCHOR}&quot;")

    def test_multiple_urls_are_linked_independently(self):
        other = "http://example.org/x"
        html = _text_to_html(f"{URL}, then {other}.")
        self.assertEqual(_hrefs(html), [URL, other])
        self.assertTrue(html.endswith("</a>."))

    def test_text_without_urls_only_gets_line_breaks(self):
        self.assertEqual(_text_to_html("Hello.\nWorld!"), "Hello.<br>\nWorld!")


class RenderEmailHtmlTests(SimpleTestCase):
    def test_plain_text_body_keeps_token_intact_before_punctuation(self):
        for body in [
            "{{login_link}}.",
            "({{login_link}})",
            "{{login_link}},",
            "Click {{login_link}}!",
            "{{ login_link }}.",
        ]:
            with self.subTest(body=body):
                html = render_email_html(personalize(body, {"login_link": URL}))
                self.assertIn(URL, _hrefs(html))
                self.assertNotIn(f'href="{URL}.', html)
                self.assertNotIn(f'href="{URL})', html)
                self.assertNotIn(f'href="{URL},', html)
                self.assertNotIn(f'href="{URL}!', html)

    def test_html_body_is_not_touched(self):
        body = f'{HTML_MARKER}<p>Go to <a href="{URL}">{URL}</a>.</p>'
        html = render_email_html(body)
        self.assertIn(f'<p>Go to <a href="{URL}">{URL}</a>.</p>', html)
        self.assertNotIn("color:#0f2d52", html)
