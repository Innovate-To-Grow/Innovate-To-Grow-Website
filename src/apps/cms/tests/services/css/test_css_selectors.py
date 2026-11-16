"""Tests for ``apps.cms.services.styles.css_selectors`` (which classes a stylesheet defines, scopes or hooks on)."""

import json
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.css_selectors import (
    ROOT_ELEMENTS,
    ClassIndex,
    css_class_index,
)

REAL_INDEX_CSS = Path(settings.BASE_DIR).parent / "pages" / "src" / "index.css"
# The frozen seed the stylesheet migrations read: realistic CSS for the parser.
SEED_SHEETS = Path(settings.BASE_DIR) / "apps" / "cms" / "migrations" / "data" / "stylesheets.json"


def load_seed_sheets():
    return {record["fields"]["name"]: record["fields"] for record in json.loads(SEED_SHEETS.read_text("utf-8"))}


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
