from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.css_selectors import (
    PASS_THROUGH_PSEUDOS,
)
from apps.cms.tests.services.css.test_css_selectors import index_of, rule


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
