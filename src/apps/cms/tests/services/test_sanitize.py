from django.test import SimpleTestCase, TestCase
from django.utils.html import conditional_escape

from apps.cms.models import CMSEmbedAllowedHost
from apps.cms.services import embed_hosts
from apps.cms.services.sanitize import (
    _iframe_attr_filter,
    sanitize_html,
    sanitize_html_for_render,
    validate_safe_url,
)


class ValidateSafeUrlTests(SimpleTestCase):
    def test_non_string_is_unsafe(self):
        self.assertFalse(validate_safe_url(None))
        self.assertFalse(validate_safe_url(123))

    def test_empty_string_is_unsafe(self):
        self.assertFalse(validate_safe_url(""))
        self.assertFalse(validate_safe_url("   "))

    def test_relative_and_fragment_urls_are_safe(self):
        for url in ("#anchor", "/path", "./rel", "../up"):
            self.assertTrue(validate_safe_url(url))

    def test_scheme_relative_without_scheme_is_safe(self):
        # urlparse yields no scheme for a bare path with no protocol.
        self.assertTrue(validate_safe_url("example.com/page"))

    def test_safe_schemes_allowed(self):
        for url in ("http://x", "https://x", "mailto:a@b.com", "tel:+15551234"):
            self.assertTrue(validate_safe_url(url))

    def test_dangerous_scheme_rejected(self):
        self.assertFalse(validate_safe_url("javascript:alert(1)"))


class IframeAttrFilterTests(SimpleTestCase):
    def test_static_attrs_allowed(self):
        for attr in ("width", "height", "frameborder", "allowfullscreen", "allow"):
            self.assertTrue(_iframe_attr_filter("iframe", attr, "1"))

    def test_non_src_unknown_attr_rejected(self):
        self.assertFalse(_iframe_attr_filter("iframe", "onload", "evil()"))

    def test_malformed_src_rejected(self):
        # parse_embed_url raises InvalidEmbedURL for an unparseable src.
        self.assertFalse(_iframe_attr_filter("iframe", "src", "javascript:alert(1)"))


class SanitizeHtmlForRenderTests(SimpleTestCase):
    def test_returns_safe_sanitized_cms_html(self):
        html = '<p>Hello <strong>CMS</strong></p><script>alert("xss")</script><a href="javascript:evil()">bad</a>'

        rendered = sanitize_html_for_render(html)

        self.assertEqual(conditional_escape(rendered), rendered)
        self.assertIn("<strong>CMS</strong>", rendered)
        self.assertNotIn("<script", rendered)
        self.assertNotIn("javascript:", rendered)

    def test_empty_input_returns_safe_empty_string(self):
        self.assertEqual(sanitize_html_for_render(None), "")
        self.assertEqual(conditional_escape(sanitize_html_for_render(None)), "")

    def test_inline_style_attribute_is_dropped(self):
        rendered = sanitize_html_for_render('<p style="position:fixed;top:0;background:red">x</p>')
        self.assertNotIn("style=", rendered)


class SanitizeIframeAllowlistTests(TestCase):
    def setUp(self):
        embed_hosts.invalidate_cache()
        self.addCleanup(embed_hosts.invalidate_cache)
        CMSEmbedAllowedHost.objects.create(hostname="www.youtube.com", is_active=True)

    def test_iframe_with_allowlisted_https_host_is_kept(self):
        html = '<iframe src="https://www.youtube.com/embed/abc"></iframe>'
        self.assertIn("https://www.youtube.com/embed/abc", sanitize_html(html))

    def test_iframe_with_unlisted_host_loses_src(self):
        html = '<iframe src="https://evil.example.com/x"></iframe>'
        self.assertNotIn("evil.example.com", sanitize_html(html))

    def test_iframe_with_javascript_scheme_loses_src(self):
        html = '<iframe src="javascript:alert(1)"></iframe>'
        rendered = sanitize_html(html)
        self.assertNotIn("javascript:", rendered)

    def test_iframe_with_http_scheme_loses_src(self):
        # parse_embed_url rejects non-https; even allowlisted hosts cannot downgrade.
        html = '<iframe src="http://www.youtube.com/embed/abc"></iframe>'
        self.assertNotIn("http://www.youtube.com", sanitize_html(html))
