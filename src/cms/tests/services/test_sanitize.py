from django.test import SimpleTestCase, TestCase
from django.utils.html import conditional_escape

from cms.models import CMSEmbedAllowedHost
from cms.services import embed_hosts
from cms.services.sanitize import sanitize_html, sanitize_html_for_render


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
