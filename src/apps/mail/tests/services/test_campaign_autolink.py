"""Plain-text campaign bodies: URL auto-linking must not absorb trailing punctuation.

The campaign ``{{login_link}}`` token is exactly 64 characters. If the auto-linker swallows a
trailing ``.`` / ``)`` / ``,`` / ``!`` into the href, the emailed link carries a 65-character token
and ``/mail/login-link/`` answers "Invalid login link.".
"""

import re
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, LoginLinkToken, RecipientLog
from apps.mail.services.campaign.personalize import personalize
from apps.mail.services.campaign.preview import HTML_MARKER, _text_to_html, render_email_html
from apps.mail.services.send_campaign.runner import _send_one_recipient
from apps.mail.services.send_campaign.transport import SesSendResult

URL = "https://i2g.example/login-link#token=" + "aB3_-" * 12 + "wxyz"
ANCHOR = f'<a href="{URL}" style="color:#0f2d52;">{URL}</a>'
HREF_RE = re.compile(r'href="([^"]*)"')


def _hrefs(html):
    return HREF_RE.findall(html)


class TextToHtmlTrailingPunctuationTests(SimpleTestCase):
    def test_token_fixture_is_64_chars(self):
        self.assertEqual(len(URL.split("#token=")[1]), 64)

    def test_trailing_punctuation_is_emitted_after_the_anchor(self):
        for punctuation in [".", ",", ";", ":", "!", "?", ")", "]", "}", "'", '"', "’", "”"]:
            with self.subTest(punctuation=punctuation):
                html = _text_to_html(f"{URL}{punctuation}")
                self.assertEqual(_hrefs(html), [URL])
                self.assertIn(f"{ANCHOR}{_text_to_html(punctuation)}", html)

    def test_wrapped_in_parentheses(self):
        html = _text_to_html(f"({URL})")
        self.assertEqual(html, f"({ANCHOR})")

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


class PlainTextLoginLinkSendPathTests(TestCase):
    """Render a real plain-text campaign body through the send path (only the provider is mocked)."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()
        self.config = EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
            max_send_rate=0,
        )
        self.member = make_member(email="reader@example.com", first_name="Rita", last_name="Reader")
        self.recipient = {
            "member_id": self.member.pk,
            "email": "reader@example.com",
            "full_name": "Rita Reader",
            "first_name": "Rita",
            "last_name": "Reader",
        }

    def _send(self, body):
        campaign = EmailCampaign.objects.create(
            subject="Sign in",
            body=body,
            audience_type="subscribers",
            member_email_scope="primary",
            status="sending",
            include_unsubscribe_header=False,
        )
        with patch("apps.mail.services.send_campaign.runner._send_via_ses") as mock_send:
            mock_send.return_value = SesSendResult(message_id="SES-001")
            _send_one_recipient(campaign, self.config, MagicMock(), "", self.recipient)
        log = RecipientLog.objects.get(campaign=campaign, email_address="reader@example.com")
        self.assertEqual(log.status, "sent", log.error_message)
        mock_send.assert_called_once()
        return campaign, mock_send.call_args.kwargs["html_body"]

    def test_login_link_followed_by_punctuation_still_logs_in(self):
        for body in [
            "Sign in here: {{login_link}}.",
            "({{login_link}})",
            "Sign in here: {{login_link}},",
            "Click {{login_link}}!",
            "Sign in here: {{ login_link }}.",
        ]:
            with self.subTest(body=body):
                campaign, html = self._send(body)

                hrefs = [href for href in _hrefs(html) if "/login-link#token=" in href]
                self.assertEqual(len(hrefs), 1)
                token = hrefs[0].split("#token=", 1)[1]
                self.assertEqual(len(token), 64)
                link = LoginLinkToken.objects.get(token=token)
                self.assertEqual(link.campaign, campaign)
                self.assertFalse(link.is_used)

                response = self.client.post("/mail/login-link/", {"token": token}, format="json")

                self.assertEqual(response.status_code, 200, response.data)
                self.assertIn("access", response.data)
                link.refresh_from_db()
                self.assertTrue(link.is_used)
