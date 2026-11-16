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

    def test_escaped_function_names_are_read_unescaped(self):
        # ``\65`` is "e" and ``\75`` is "u": the browser reads expression() and url().
        cases = {
            ".a { width: \\65xpression(1); }": "expression() is not allowed",
            ".a { background: \\75rl(javascript:void0); }": "javascript: URLs are not allowed",
        }
        for css, message in cases.items():
            with self.subTest(css=css):
                self.assertTrue(any(message in error for error in custom_css_errors(css)), custom_css_errors(css))

    def test_escapes_that_decode_to_a_lone_surrogate_do_not_raise(self):
        # tinycss2 < 1.5.0 raised UnicodeEncodeError on these (a 500 from the Site Settings form).
        for css in (".a { width: 1\\d800; }", ".a { width: \\d800(1); }", ":\\d800(.x) { color: red; }"):
            with self.subTest(css=css):
                self.assertEqual(custom_css_errors(css), [])

    def test_forbidden_constructs_inside_bracket_and_paren_blocks_are_refused(self):
        for css in (".a { grid-template-columns: [expression(1)] 1fr; }", ".a { width: (expression(1)); }"):
            with self.subTest(css=css):
                self.assertEqual(custom_css_errors(css), ["Line 1, column 6: expression() is not allowed."])

    def test_errors_point_at_the_rule_or_declaration(self):
        css = ".a { color: red; }\n@media print {\n  .b {\n    behavior: url(x.htc);\n  }\n}\n"
        self.assertEqual(custom_css_errors(css), ["Line 4, column 5: the behavior property is not allowed."])

    def test_a_rule_the_parser_drops_is_reported(self):
        # The stray } starts a rule that never gets a block, so the parser drops it.
        errors = custom_css_errors(".a { color: red; } }")
        self.assertEqual(errors[0], "Line 1, column 20: this } closes no block.")
        self.assertEqual(len(errors), 2)
        self.assertTrue(errors[1].startswith("Line 1, column 20: EOF reached before {} block"), errors)

    def test_statement_at_rules_without_a_block_pass(self):
        self.assertEqual(custom_css_errors("@layer base, overrides;\n.a { color: red; }"), [])
