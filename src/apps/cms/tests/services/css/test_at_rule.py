from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.css_selectors import (
    GROUPING_AT_RULES,
    SCOPING_AT_RULES,
    css_class_index,
)
from apps.cms.tests.services.css.test_css_selectors import REAL_INDEX_CSS, index_of, load_seed_sheets, rule


class AtRuleTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_grouping_at_rules_are_walked(self):
        self.assertTrue({"media", "supports", "layer", "container"} <= GROUPING_AT_RULES)
        for prelude in (
            "@media (min-width: 768px)",
            "@supports (display: grid)",
            "@supports selector(.ghost)",
            "@layer itg-maintenance-fallback",
            "@layer",
            "@container card (min-width: 400px)",
            "@MEDIA screen",
        ):
            with self.subTest(prelude=prelude):
                self.assertEqual(index_of(prelude + " { .x { } .p .q { } }"), ({"x"}, {"q"}, {"p"}))

    def test_nested_grouping_at_rules_are_walked(self):
        css = "@media screen { @supports (display: grid) { @layer l { .deep { } } } }"
        self.assertEqual(index_of(css), ({"deep"}, set(), set()))

    def test_a_declaration_inside_a_grouping_at_rule_does_not_swallow_the_next_rule(self):
        self.assertEqual(index_of("@media print { color: red; .x { } }"), ({"x"}, set(), set()))

    def test_statement_at_rules_do_not_stop_the_scan(self):
        css = "@import url('x.css');\n@layer a, b;\n@charset 'utf-8';\n.after { }"
        self.assertEqual(index_of(css), ({"after"}, set(), set()))

    def test_scope_content_is_scoped(self):
        self.assertEqual(SCOPING_AT_RULES, frozenset({"scope"}))
        for css in (
            "@scope (.card) { .title { } }",
            "@scope (.card) to (.content) { .title { } }",
            "@scope { .title { } }",
            "@media print { @scope (.card) { .title { } } }",
            "@scope (.card) { @media print { .title { } } }",
        ):
            with self.subTest(css=css):
                self.assertEqual(index_of(css), (set(), {"title"}, set()))
        self.assertEqual(index_of("@scope (.card) { .wrap .title { } }"), (set(), {"title"}, {"wrap"}))

    def test_keyframes_font_face_page_and_unknown_at_rules_add_nothing(self):
        for css in (
            "@keyframes spin { from { } 50.5% { } to { } }",
            "@font-face { font-family: X; src: url(a.woff2) format('woff2'); }",
            "@page :first { margin: 1in; }",
            "@unknown { .x { } }",
        ):
            with self.subTest(css=css):
                self.assertEqual(index_of(css), (set(), set(), set()))
        self.assertEqual(index_of("@keyframes spin { to { } }\n.b { }"), ({"b"}, set(), set()))


class TokenizerTests(SimpleTestCase):
    """Strings, URLs, attribute selectors, escapes and comments are read the way a browser reads them."""

    def setUp(self):
        cache.clear()

    def test_braces_and_classes_inside_strings_are_ignored(self):
        css = '.a::before { content: ".ghost{"; }\n.b { }'
        self.assertEqual(index_of(css), ({"a", "b"}, set(), set()))

    def test_data_uris_with_an_embedded_style_block_are_ignored(self):
        for url in (
            'url("data:image/svg+xml,<style>.st0{fill:red}</style>")',
            "url('data:image/svg+xml,<style>.st0{fill:red}</style>')",
            "url(data:image/svg+xml,<style>.st0{fill:red}</style>)",
        ):
            with self.subTest(url=url):
                css = f".a {{ background: {url}; }}\n.b {{ }}"
                self.assertEqual(index_of(css), ({"a", "b"}, set(), set()))

    def test_attribute_selectors_do_not_misparse(self):
        self.assertEqual(rule('a[href$=".pdf"]'), (set(), set(), set()))
        self.assertEqual(rule('a[href$=".pdf"].x'), ({"x"}, set(), set()))
        self.assertEqual(rule('[data-x=".y"]'), (set(), set(), set()))
        self.assertEqual(rule('[class~="x"] .y'), (set(), {"y"}, set()))

    def test_a_bracket_inside_an_attribute_string_does_not_swallow_the_rest(self):
        self.assertEqual(rule('[title="(a"] .x'), (set(), {"x"}, set()))
        self.assertEqual(index_of('[title="(a"] .x { }\n.after { }'), ({"after"}, {"x"}, set()))

    def test_escaped_class_names_are_unescaped(self):
        self.assertEqual(rule(".md\\:hidden"), ({"md:hidden"}, set(), set()))
        self.assertEqual(rule(".w-1\\/2"), ({"w-1/2"}, set(), set()))
        self.assertEqual(rule(".\\31 0"), ({"10"}, set(), set()))

    def test_escapes_that_decode_to_a_lone_surrogate_do_not_raise(self):
        # tinycss2 < 1.5.0 raised UnicodeEncodeError on an escaped surrogate in a unit or function name.
        self.assertEqual(index_of(".a { width: 1\\d800; }"), ({"a"}, set(), set()))
        self.assertEqual(index_of(".a { width: \\d800(1); }"), ({"a"}, set(), set()))
        self.assertEqual(rule(":\\d800(.x)"), (set(), {"x"}, set()))

    def test_comments_are_ignored(self):
        css = "/* .ghost { } */\n.real { }\n/*\n  .also-ghost { }\n*/\n/* .x */ .y .z { }"
        self.assertEqual(index_of(css), ({"real"}, {"z"}, {"y"}))

    def test_a_comment_inside_a_selector(self):
        # Surrounded by whitespace it sits in a descendant combinator; on its own it joins one compound.
        self.assertEqual(rule(".a /* .ghost */ .b"), (set(), {"b"}, {"a"}))
        self.assertEqual(rule(".a/**/.b"), (set(), {"a", "b"}, set()))


class RealCssTests(SimpleTestCase):
    """The repo seed and ``pages/src/index.css``: what they style only in context is not defined."""

    def setUp(self):
        cache.clear()
        self.seeds = load_seed_sheets()

    def _index(self, sheet_name):
        return css_class_index(self.seeds[sheet_name]["css"])

    def test_submission_section_title_is_not_defined_in_cms_blocks(self):
        index = self._index("cms-blocks")

        self.assertNotIn("submission-section-title", index.defined)
        # Styled inside .cms-prose / :has(), and a hook for the button rule that follows it.
        self.assertIn("submission-section-title", index.scoped)
        self.assertIn("submission-section-title", index.context)
        self.assertIn("cms-prose", index.defined)

    def test_is_mobile_open_is_not_defined_in_layout_menu(self):
        index = self._index("layout-menu")

        self.assertNotIn("is-mobile-open", index.defined)
        # Only mentioned in "#menu-root:has(.site-header.is-mobile-open)".
        self.assertIn("is-mobile-open", index.scoped)
        self.assertIn("site-header", index.defined)

    def test_sr_only_is_defined_in_the_frontend_index_css(self):
        css = REAL_INDEX_CSS.read_text(encoding="utf-8")

        self.assertIn("body .sr-only", css)
        self.assertIn("sr-only", css_class_index(css).defined)

    def test_every_seed_sheet_parses_and_no_defined_class_is_also_scoped_or_context(self):
        all_defined = set()
        for name, fields in self.seeds.items():
            with self.subTest(sheet=name):
                index = css_class_index(fields["css"])
                self.assertFalse(index.defined & (index.scoped | index.context))
                all_defined |= index.defined
        # Every sheet but the page-projects stub styles something.
        self.assertGreater(len(all_defined), 100)
