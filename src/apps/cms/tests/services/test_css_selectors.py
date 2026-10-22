"""Tests for ``apps.cms.services.styles.css_selectors`` (which classes a stylesheet defines, scopes or hooks on)."""

from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.css_selectors import (
    GROUPING_AT_RULES,
    PASS_THROUGH_PSEUDOS,
    ROOT_ELEMENTS,
    SCOPING_AT_RULES,
    ClassIndex,
    css_class_index,
)
from apps.cms.services.styles.drift import load_seed_sheets

REAL_INDEX_CSS = Path(settings.BASE_DIR).parent / "pages" / "src" / "index.css"


def index_of(css):
    """``(defined, scoped, context)`` of a stylesheet."""
    index = css_class_index(css)
    return index.defined, index.scoped, index.context


def rule(selector):
    """``(defined, scoped, context)`` of one empty rule with ``selector``."""
    return index_of(selector + " {}")


class ClassIndexTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_css_class_index_returns_a_class_index(self):
        index = css_class_index(".a {}")

        self.assertIsInstance(index, ClassIndex)
        self.assertEqual(index, ClassIndex(defined={"a"}, scoped=set(), context=set()))

    def test_each_index_gets_its_own_sets(self):
        first = ClassIndex()
        first.defined.add("x")

        self.assertEqual(ClassIndex(), ClassIndex(defined=set(), scoped=set(), context=set()))

    def test_finalize_removes_defined_classes_from_scoped_and_context(self):
        index = ClassIndex(defined={"a"}, scoped={"a", "b"}, context={"a", "b", "c"})

        self.assertIs(index.finalize(), index)
        # Defined wins over the other two; a class can stay both scoped and context.
        self.assertEqual((index.defined, index.scoped, index.context), ({"a"}, {"b"}, {"b", "c"}))

    def test_defined_wins_whatever_the_rule_order(self):
        for css in (
            ".wrap .card {}\n.card {}",
            ".card {}\n.wrap .card {}",
            ".card .title {}\n.card {}",
            ".card.is-open {}\n.card:hover {}",
        ):
            with self.subTest(css=css):
                defined, scoped, context = index_of(css)
                self.assertIn("card", defined)
                self.assertNotIn("card", scoped | context)

    def test_a_class_can_be_both_scoped_and_context(self):
        self.assertEqual(index_of(".p .x {}\n.x .y {}"), (set(), {"x", "y"}, {"p", "x"}))


class SubjectTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_the_only_class_of_a_subject_without_context_is_defined(self):
        for selector in (
            ".x",
            ".x:hover",
            ".x::before",
            ".x:hover:focus-visible",
            ".x:nth-child(2n + 1)",
            "p.x",
            "a.x",
            "*.x",
            "#id.x",
            ".x[data-y='a b']",
            "  .x  ",
        ):
            with self.subTest(selector=selector):
                self.assertEqual(rule(selector), ({"x"}, set(), set()))

    def test_a_subject_with_more_than_one_class_scopes_every_class(self):
        for selector, classes in (
            (".btn.is-active", {"btn", "is-active"}),
            (".a.x:hover", {"a", "x"}),
            ("a.btn.primary", {"btn", "primary"}),
            (".a.b.c", {"a", "b", "c"}),
        ):
            with self.subTest(selector=selector):
                self.assertEqual(rule(selector), (set(), classes, set()))

    def test_a_class_defined_on_its_own_elsewhere_is_only_defined(self):
        self.assertEqual(index_of(".btn.is-active {}\n.btn {}"), ({"btn"}, {"is-active"}, set()))

    def test_each_selector_of_a_list_is_judged_on_its_own(self):
        self.assertEqual(rule(".a, .b .c"), ({"a"}, {"c"}, {"b"}))
        self.assertEqual(index_of(".a,.b{}"), ({"a", "b"}, set(), set()))
        self.assertEqual(rule(".a, , .b"), ({"a", "b"}, set(), set()))

    def test_declarations_add_nothing(self):
        css = ".a { margin: .5rem; width: calc(100% - .25rem); }\n.b{color:red}.c{}"
        self.assertEqual(index_of(css), ({"a", "b", "c"}, set(), set()))

    def test_empty_input(self):
        for css in ("", None, "  \n", "/* only a comment */"):
            with self.subTest(css=css):
                self.assertEqual(index_of(css), (set(), set(), set()))

    def test_malformed_css_does_not_raise(self):
        self.assertEqual(index_of(".a {"), ({"a"}, set(), set()))
        self.assertEqual(index_of(".a { color: red"), ({"a"}, set(), set()))
        defined, scoped, context = index_of("}}} .x {")
        self.assertEqual((defined, context), (set(), set()))
        self.assertLessEqual(scoped, {"x"})


class RootElementTests(SimpleTestCase):
    """A leading ``html`` / ``body`` / ``:root`` followed by a space matches every element."""

    def setUp(self):
        cache.clear()

    def test_root_elements(self):
        self.assertEqual(ROOT_ELEMENTS, frozenset({"html", "body"}))

    def test_a_leading_root_element_before_a_descendant_combinator_is_dropped(self):
        for selector in (
            "body .x",
            "html .x",
            ":root .x",
            "html body .x",
            ":root body .x",
            "BODY .x",
            ":ROOT .x",
            "body  .x",
            "body\n.x",
            "body /* note */ .x",
        ):
            with self.subTest(selector=selector):
                self.assertEqual(rule(selector), ({"x"}, set(), set()))

    def test_other_combinators_after_a_root_element_keep_the_class_scoped(self):
        for selector in ("body > .x", "body ~ .x", "body + .x", "html > body .x"):
            with self.subTest(selector=selector):
                self.assertEqual(rule(selector), (set(), {"x"}, set()))

    def test_a_root_element_with_more_than_its_name_is_context(self):
        self.assertEqual(rule("html[data-x] .x"), (set(), {"x"}, set()))
        self.assertEqual(rule("body:not(.y) .x"), (set(), {"x", "y"}, set()))
        self.assertEqual(rule("html.dark .x"), (set(), {"x"}, {"dark"}))

    def test_only_leading_root_elements_are_dropped(self):
        self.assertEqual(rule("body .p .x"), (set(), {"x"}, {"p"}))
        self.assertEqual(rule(".page body .x"), (set(), {"x"}, {"page"}))
        self.assertEqual(rule("body.x"), ({"x"}, set(), set()))

    def test_a_root_element_alone_adds_nothing(self):
        for selector in ("body", "html", ":root"):
            with self.subTest(selector=selector):
                self.assertEqual(rule(selector), (set(), set(), set()))


class ContextTests(SimpleTestCase):
    """Classes in a compound before a combinator are context (a hook other rules hang on)."""

    def setUp(self):
        cache.clear()

    def test_every_combinator_makes_the_earlier_class_context_and_scopes_the_subject(self):
        for selector in (
            ".p .x",
            ".p  .x",
            ".p\n.x",
            ".p\t.x",
            ".p>.x",
            ".p > .x",
            ".p+.x",
            ".p + .x",
            ".p~.x",
            ".p ~ .x",
        ):
            with self.subTest(selector=selector):
                self.assertEqual(rule(selector), (set(), {"x"}, {"p"}))

    def test_a_page_wrapper_class_is_context(self):
        self.assertEqual(rule(".page .x"), (set(), {"x"}, {"page"}))
        self.assertEqual(rule(".page .x:hover"), (set(), {"x"}, {"page"}))

    def test_every_context_compound_counts(self):
        self.assertEqual(rule(".a .b > .x"), (set(), {"x"}, {"a", "b"}))
        self.assertEqual(rule(".page.dark .x"), (set(), {"x"}, {"page", "dark"}))
        self.assertEqual(rule(".x *"), (set(), set(), {"x"}))

    def test_element_and_universal_compounds_scope_without_context(self):
        self.assertEqual(rule("div .x"), (set(), {"x"}, set()))
        self.assertEqual(rule("ul > li.x"), (set(), {"x"}, set()))

    def test_whitespace_inside_an_attribute_value_is_not_a_combinator(self):
        self.assertEqual(rule("[data-x='a b'] .c"), (set(), {"c"}, set()))
        self.assertEqual(rule(".a[data-x='.b c']"), ({"a"}, set(), set()))


class PassThroughPseudoTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_pass_through_set(self):
        self.assertTrue({"is", "where", "matches"} <= PASS_THROUGH_PSEUDOS)
        self.assertTrue({"not", "has", "nth-child"}.isdisjoint(PASS_THROUGH_PSEUDOS))

    def test_is_with_a_selector_list_defines_every_argument(self):
        self.assertEqual(rule(":is(.a, .b)"), ({"a", "b"}, set(), set()))
        self.assertEqual(rule(":is( .a , .b )"), ({"a", "b"}, set(), set()))

    def test_where_matches_and_vendor_any_pass_through(self):
        for selector in (":where(.x)", ":matches(.x)", ":-webkit-any(.x)", ":-moz-any(.x)", ":IS(.x)", ":Where(.x)"):
            with self.subTest(selector=selector):
                self.assertEqual(rule(selector), ({"x"}, set(), set()))

    def test_arguments_are_analysed_as_selectors(self):
        self.assertEqual(rule(":is(.wrap .r)"), (set(), {"r"}, {"wrap"}))
        self.assertEqual(rule(":is(.a.b)"), (set(), {"a", "b"}, set()))
        self.assertEqual(rule(":is(body .x)"), ({"x"}, set(), set()))

    def test_each_argument_is_judged_on_its_own(self):
        self.assertEqual(rule(":is(.a, .wrap .b)"), ({"a"}, {"b"}, {"wrap"}))
        self.assertEqual(rule(":is(:where(.a), .b)"), ({"a", "b"}, set(), set()))

    def test_in_a_subject_with_context_the_arguments_are_scoped(self):
        self.assertEqual(rule(".page :is(.a, .b)"), (set(), {"a", "b"}, {"page"}))
        self.assertEqual(rule(".page :is(.p .q)"), (set(), {"q"}, {"page", "p"}))

    def test_in_a_context_compound_every_argument_class_is_context(self):
        self.assertEqual(rule(":is(.x) .y"), (set(), {"y"}, {"x"}))
        self.assertEqual(rule(":where(.wrap) .x"), (set(), {"x"}, {"wrap"}))
        self.assertEqual(rule(":is(.p .q) .y"), (set(), {"y"}, {"p", "q"}))
        self.assertEqual(rule(":is(.a, .b) > .c"), (set(), {"c"}, {"a", "b"}))

    def test_in_a_nested_rule_the_arguments_are_scoped(self):
        self.assertEqual(index_of(".outer { :is(.a, .b) { } }"), ({"outer"}, {"a", "b"}, set()))

    def test_a_class_beside_a_pass_through_shares_the_subject(self):
        # ".a:is(.b)" matches what ".a.b" matches, so both classes are needed and both are scoped.
        self.assertEqual(rule(".a:is(.b)"), (set(), {"a", "b"}, set()))


class MentionOnlyPseudoTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_not_has_and_nth_child_of_only_mention_a_class(self):
        for selector, defined in (
            (".a:not(.x)", {"a"}),
            (":not(.x)", set()),
            (".a:has(.x)", {"a"}),
            (".a:has(> .x)", {"a"}),
            ("li:nth-child(2 of .x)", set()),
            (":nth-last-child(odd of .x)", set()),
            (".a:not(:is(.x))", {"a"}),
            # A parenthesised group inside a functional pseudo-class is searched too.
            (".a:has((.x))", {"a"}),
            ("(.x)", set()),
        ):
            with self.subTest(selector=selector):
                self.assertEqual(rule(selector), (defined, {"x"}, set()))

    def test_every_class_inside_is_mentioned_with_no_context(self):
        self.assertEqual(rule(".x:has(.y, .z)"), ({"x"}, {"y", "z"}, set()))
        self.assertEqual(rule(".a:not(.b .c)"), ({"a"}, {"b", "c"}, set()))

    def test_a_mention_inside_a_context_compound_is_scoped(self):
        self.assertEqual(rule(".page:not(.y) .x"), (set(), {"x", "y"}, {"page"}))

    def test_pass_through_and_mention_only_in_one_compound(self):
        self.assertEqual(rule(":is(.a):not(.b)"), ({"a"}, {"b"}, set()))
        self.assertEqual(rule(".a:has(> .c):hover"), ({"a"}, {"c"}, set()))


class NestedRuleTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_a_rule_nested_in_another_rule_is_scoped(self):
        self.assertEqual(index_of(".outer { .inner { } }"), ({"outer"}, {"inner"}, set()))
        self.assertEqual(index_of(".a { .b { .c { } } }"), ({"a"}, {"b", "c"}, set()))

    def test_nested_rules_after_declarations_and_with_ampersand(self):
        css = ".outer { color: red; .inner { color: blue; } &.mod { } & .kid { } &:hover { } }"
        self.assertEqual(index_of(css), ({"outer"}, {"inner", "mod", "kid"}, set()))

    def test_context_in_a_nested_rule_is_still_context(self):
        self.assertEqual(index_of(".outer { .inner .deep { } }"), ({"outer"}, {"deep"}, {"inner"}))

    def test_a_root_element_does_not_lift_a_nested_rule_out_of_its_parent(self):
        self.assertEqual(index_of(".outer { body .x { } }"), ({"outer"}, {"x"}, set()))

    def test_rules_inside_an_at_rule_nested_in_a_rule_are_scoped(self):
        self.assertEqual(index_of(".outer { @media (min-width: 1px) { .inner { } } }"), ({"outer"}, {"inner"}, set()))
        css = ".outer { @media print { color: red; .inner { } } }"
        self.assertEqual(index_of(css), ({"outer"}, {"inner"}, set()))

    def test_nesting_inside_a_grouping_at_rule(self):
        self.assertEqual(index_of("@media print { .outer { .nested { } } }"), ({"outer"}, {"nested"}, set()))


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
