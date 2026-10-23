from django.test import SimpleTestCase

from apps.cms.services.styles.custom_css import MAX_CUSTOM_CSS_BYTES, custom_css_errors


class CustomCssErrorsTests(SimpleTestCase):
    def test_ordinary_css_passes(self):
        css = """
/* Brand tweak */
.site-header-band { background: #0f2d52; }
@media (max-width: 768px) {
  .cms-hero h1 { font-size: 2rem; }
}
@supports (display: grid) { .itg-grid-cards { gap: 24px; } }
.icon::before { content: "{"; background: url("/media/a.png"); }
"""
        self.assertEqual(custom_css_errors(css), [])

    def test_empty_css_passes(self):
        self.assertEqual(custom_css_errors(""), [])

    def test_an_unclosed_brace_is_reported_with_its_position(self):
        errors = custom_css_errors(".a { color: red; }\n.b {\n  color: blue;\n")
        self.assertEqual(errors, ["Line 2, column 4: this { is never closed."])

    def test_a_stray_closing_brace_is_reported(self):
        errors = custom_css_errors(".a { color: red; }\n}\n.b { color: blue; }")
        self.assertIn("Line 2, column 1: this } closes no block.", errors)

    def test_braces_inside_strings_and_comments_do_not_count(self):
        self.assertEqual(custom_css_errors('.a::after { content: "}"; } /* { */'), [])

    def test_at_rules_that_must_open_a_sheet_are_refused(self):
        for css in ('@import url("https://example.com/x.css");', '@charset "utf-8";', "@namespace svg url(x);"):
            with self.subTest(css=css):
                errors = custom_css_errors(css)
                self.assertEqual(len(errors), 1)
                self.assertIn("is not allowed in custom CSS", errors[0])

    def test_script_like_constructs_are_refused_even_when_nested(self):
        cases = {
            ".a { width: expression(alert(1)); }": "expression() is not allowed",
            ".a { behavior: url(x.htc); }": "the behavior property is not allowed",
            ".a { -moz-binding: url(x.xml#y); }": "the -moz-binding property is not allowed",
            # Unquoted, the parentheses make it a bad URL, which a browser drops; it is reported as broken.
            ".a { background: url(javascript:alert(1)); }": "bad URL token",
            ".a { background: url(javascript:void0); }": "javascript: URLs are not allowed",
            '.a { background: url("javascript:alert(1)"); }': "javascript: URLs are not allowed",
            "@media print { .a { width: calc(1px + expression(1)); } }": "expression() is not allowed",
        }
        for css, message in cases.items():
            with self.subTest(css=css):
                self.assertTrue(any(message in error for error in custom_css_errors(css)), custom_css_errors(css))

    def test_the_size_limit(self):
        css = ".a { color: red; }\n" * (MAX_CUSTOM_CSS_BYTES // 19 + 1)
        self.assertEqual(
            custom_css_errors(css), [f"Custom CSS is {len(css)} bytes; the limit is {MAX_CUSTOM_CSS_BYTES}."]
        )
