from django.test import SimpleTestCase
from django.utils.html import conditional_escape

from cms.services.sanitize import sanitize_html_for_render


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
