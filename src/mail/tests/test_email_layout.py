"""Tests for the shared email layout module."""

from django.test import TestCase

from mail.services.email_layout import get_logo_data_uri, get_logo_inline_image, render_email_layout


class RenderEmailLayoutTest(TestCase):
    """Tests for render_email_layout()."""

    def test_wraps_content_with_header_and_footer(self):
        html = render_email_layout("<p>Hello World</p>")
        self.assertIn("<p>Hello World</p>", html)
        self.assertIn("Innovate to Grow", html)
        self.assertIn("UC Merced", html)
        # Footer
        self.assertIn("Innovate to Grow &mdash; UC Merced", html)

    def test_default_logo_src_is_cid(self):
        html = render_email_layout("<p>Test</p>")
        self.assertIn('src="cid:i2g-logo"', html)

    def test_custom_logo_src(self):
        html = render_email_layout("<p>Test</p>", logo_src="https://example.com/logo.png")
        self.assertIn('src="https://example.com/logo.png"', html)
        self.assertNotIn("cid:i2g-logo", html)

    def test_empty_logo_src_omits_img(self):
        html = render_email_layout("<p>Test</p>", logo_src="")
        self.assertNotIn("<img", html)
        # Header text still present
        self.assertIn("Innovate to Grow", html)


class GetLogoInlineImageTest(TestCase):
    """Tests for get_logo_inline_image()."""

    def test_returns_three_tuple(self):
        result = get_logo_inline_image()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_cid_and_filename(self):
        cid, filename, data = get_logo_inline_image()
        self.assertEqual(cid, "i2g-logo")
        self.assertEqual(filename, "i2glogo.png")

    def test_bytes_not_empty(self):
        _, _, data = get_logo_inline_image()
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 0)


class GetLogoDataUriTest(TestCase):
    """Tests for get_logo_data_uri()."""

    def test_returns_data_uri(self):
        uri = get_logo_data_uri()
        self.assertTrue(uri.startswith("data:image/png;base64,"))

    def test_uri_is_non_empty(self):
        uri = get_logo_data_uri()
        # Should have actual base64 data after the prefix
        self.assertGreater(len(uri), len("data:image/png;base64,"))
