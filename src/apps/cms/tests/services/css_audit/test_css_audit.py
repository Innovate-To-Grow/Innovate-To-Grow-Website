"""Tests for the scanners in ``apps.cms.services.styles.audit``: class tokens, CSS indexes, content usage.

The report built from them (``audit_css_classes``) is covered in ``test_css_audit_report``.
"""

import tempfile
from pathlib import Path

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.audit import (
    class_tokens_in_html,
    iter_html_fields,
)

EMPTY_MAPS = {"defined": {}, "scoped": {}, "hook": {}}

# main.tsx statically imports index.css; routes/Lazy.css is reached only through React.lazy.
ENTRY_AND_ROUTE_FRONTEND = {
    "main.tsx": "import './index.css';\nimport { App } from './App';\n",
    "App.tsx": "const Lazy = React.lazy(() => import('./routes/Lazy'));\nexport const App = () => null;\n",
    "routes/Lazy.tsx": "import './Lazy.css';\nexport default function Lazy() { return null; }\n",
    "index.css": ".in-frontend {}",
    "routes/Lazy.css": ".route-only {}\n.lazy-page .route-scoped {}",
}


def make_frontend_dir(test_case, files):
    """A temp frontend source dir holding ``{relative_path: text}``."""
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


class ClassTokensInHtmlTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_double_and_single_quoted_attributes(self):
        self.assertEqual(class_tokens_in_html('<p class="lead">x</p>'), {"lead"})
        self.assertEqual(class_tokens_in_html("<p class='lead'>x</p>"), {"lead"})

    def test_unquoted_attribute(self):
        self.assertEqual(class_tokens_in_html("<p class=lead>x</p>"), {"lead"})
        self.assertEqual(class_tokens_in_html("<p class=lead id=intro>x</p>"), {"lead"})
        self.assertEqual(class_tokens_in_html("<p CLASS = lead >x</p>"), {"lead"})
        self.assertEqual(
            class_tokens_in_html('<p class=one><span class="two three">x</span></p>'), {"one", "two", "three"}
        )

    def test_entities_are_decoded(self):
        self.assertEqual(class_tokens_in_html('<p class="a&amp;b c&#45;d">x</p>'), {"a&b", "c-d"})
        self.assertEqual(class_tokens_in_html("<p class=a&amp;b>x</p>"), {"a&b"})

    def test_multiple_classes_and_elements(self):
        html = '<div class="  card card--wide\tnew ">\n<a CLASS = \'btn card\'>go</a></div><img class="pic"/>'
        self.assertEqual(class_tokens_in_html(html), {"card", "card--wide", "new", "btn", "pic"})

    def test_only_ascii_whitespace_separates_classes(self):
        # Browsers split a class attribute on space, tab, LF, FF and CR only.
        self.assertEqual(class_tokens_in_html('<p class="a\tb\nc\fd\re f">x</p>'), {"a", "b", "c", "d", "e", "f"})

    def test_a_no_break_space_is_part_of_the_class(self):
        self.assertEqual(class_tokens_in_html('<p class="solo&nbsp;wide plain">x</p>'), {"solo\u00a0wide", "plain"})
        self.assertEqual(class_tokens_in_html('<p class="solo\u00a0wide">x</p>'), {"solo\u00a0wide"})
        self.assertEqual(class_tokens_in_html('<p class="em\u2003space">x</p>'), {"em\u2003space"})
        self.assertEqual(class_tokens_in_html('<p class="v\x0btab">x</p>'), {"v\x0btab"})

    def test_attributes_that_only_end_in_class_are_ignored(self):
        html = '<p data-class="nope" data-x-class=nope2 subclass="nope3" aria-class=\'nope4\'>x</p>'
        self.assertEqual(class_tokens_in_html(html), set())
        self.assertEqual(class_tokens_in_html('<p data-class="nope" class="yes">x</p>'), {"yes"})

    def test_comments_and_script_text_are_not_markup(self):
        self.assertEqual(class_tokens_in_html('<!-- <p class="ghost"> --><p class=real>x</p>'), {"real"})
        self.assertEqual(class_tokens_in_html("<script>var s = '<p class=\"in-script\">';</script>"), set())

    def test_no_classes(self):
        self.assertEqual(class_tokens_in_html("<p>Plain <b>text</b></p>"), set())
        self.assertEqual(class_tokens_in_html('<p class="">x</p>'), set())
        self.assertEqual(class_tokens_in_html("<p class>x</p>"), set())
        self.assertEqual(class_tokens_in_html(""), set())
        self.assertEqual(class_tokens_in_html(None), set())


class IterHtmlFieldsTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_yields_only_html_keys_however_nested(self):
        data = {
            "heading": '<h2 class="not-html-key">x</h2>',
            "body_html": "<p>body</p>",
            "items": [
                {"question": "q", "answer_html": "<p>answer</p>"},
                {"title": '<b class="ignored">t</b>'},
                ["deep", {"note_html": "<i>note</i>"}],
            ],
            "footer": {"footer_html": "<small>footer</small>", "count": 3},
            "size_html": 12,
        }

        self.assertEqual(
            list(iter_html_fields(data)),
            ["<p>body</p>", "<p>answer</p>", "<i>note</i>", "<small>footer</small>"],
        )

    def test_html_key_with_a_container_value_is_searched(self):
        self.assertEqual(list(iter_html_fields({"group_html": {"inner_html": "<p>x</p>"}})), ["<p>x</p>"])

    def test_top_level_list_and_scalars(self):
        self.assertEqual(list(iter_html_fields([{"a_html": "x"}, {"b_html": "y"}])), ["x", "y"])
        self.assertEqual(list(iter_html_fields("body_html")), [])
        self.assertEqual(list(iter_html_fields(None)), [])
        self.assertEqual(list(iter_html_fields({1: "<p class=x>1</p>"})), [])
