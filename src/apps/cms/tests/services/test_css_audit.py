"""Tests for the scanners in ``apps.cms.services.styles.audit``: class tokens, CSS indexes, content usage.

The report built from them (``audit_css_classes``) is covered in ``test_css_audit_report``.
"""

import tempfile
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.cms.models import CMSBlock, CMSPage, FooterContent
from apps.cms.services.styles.audit import (
    class_tokens_in_html,
    content_class_usage,
    default_frontend_dir,
    frontend_css_index,
    iter_html_fields,
    page_css_index,
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


class FrontendCssIndexTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_without_main_tsx_every_file_counts_as_entry(self):
        root = make_frontend_dir(
            self,
            {
                "features/a/One.css": ".shared {}\n.only-a {}",
                "app/Two.css": ".shared:hover {}",
                "features/a/One.tsx": "const x = '.not-css';",
            },
        )

        index = frontend_css_index(root)

        self.assertEqual(set(index), {"defined", "scoped", "hook", "route", "graph"})
        self.assertFalse(index["graph"])
        self.assertEqual(
            dict(index["defined"]), {"shared": {"features/a/One.css", "app/Two.css"}, "only-a": {"features/a/One.css"}}
        )
        self.assertEqual((dict(index["route"]), dict(index["scoped"]), dict(index["hook"])), ({}, {}, {}))

    def test_main_tsx_splits_entry_and_route_files(self):
        root = make_frontend_dir(self, ENTRY_AND_ROUTE_FRONTEND)

        index = frontend_css_index(root)

        self.assertTrue(index["graph"])
        self.assertEqual(dict(index["defined"]), {"in-frontend": {"index.css"}})
        self.assertEqual(dict(index["route"]), {"route-only": {"routes/Lazy.css"}})
        # Scoped and hook classes are listed whichever bundle the file lands in.
        self.assertEqual(dict(index["scoped"]), {"route-scoped": {"routes/Lazy.css"}})
        self.assertEqual(dict(index["hook"]), {"lazy-page": {"routes/Lazy.css"}})

    def test_css_reached_statically_and_lazily_is_in_the_entry_bundle(self):
        root = make_frontend_dir(
            self,
            {
                **ENTRY_AND_ROUTE_FRONTEND,
                "App.tsx": (
                    "import './shared.css';\n"
                    "const Lazy = React.lazy(() => import('./routes/Lazy'));\nexport const App = () => null;\n"
                ),
                "routes/Lazy.tsx": "import '../shared.css';\nimport './Lazy.css';\nexport default () => null;\n",
                "shared.css": ".both-ways {}",
            },
        )

        index = frontend_css_index(root)

        self.assertEqual(dict(index["defined"]), {"in-frontend": {"index.css"}, "both-ways": {"shared.css"}})
        self.assertEqual(dict(index["route"]), {"route-only": {"routes/Lazy.css"}})

    def test_scoped_and_hook_classes_are_indexed_per_file(self):
        root = make_frontend_dir(
            self,
            {
                "pages/Event.css": ".event-page .lead {}\n.event-page {}",
                "pages/News.css": ".news .lead {}",
                "base.css": ".lead {}",
            },
        )

        index = frontend_css_index(root)

        self.assertEqual(dict(index["defined"]), {"event-page": {"pages/Event.css"}, "lead": {"base.css"}})
        self.assertEqual(dict(index["scoped"]), {"lead": {"pages/Event.css", "pages/News.css"}})
        # A file that defines a class is not listed as hooking on it.
        self.assertEqual(dict(index["hook"]), {"news": {"pages/News.css"}})

    def test_dependency_build_and_test_dirs_are_not_indexed(self):
        root = make_frontend_dir(
            self,
            {
                "kept.css": ".kept {}",
                "node_modules/pkg/x.css": ".pkg {}",
                "dist/assets/index.css": ".built {}",
                "__tests__/fixture.css": ".fixture {}",
            },
        )
        self.assertEqual(dict(frontend_css_index(root)["defined"]), {"kept": {"kept.css"}})

    def test_accepts_string_path(self):
        root = make_frontend_dir(self, {"x.css": ".x {}"})
        self.assertEqual(dict(frontend_css_index(str(root))["defined"]), {"x": {"x.css"}})

    def test_missing_dir_returns_empty(self):
        missing = make_frontend_dir(self, {}) / "no-such-frontend"

        self.assertEqual(frontend_css_index(missing), {**EMPTY_MAPS, "route": {}, "graph": False})

    def test_default_frontend_dir_is_pages_src(self):
        self.assertEqual(default_frontend_dir(), Path(settings.BASE_DIR).parent / "pages" / "src")

    def test_default_dir_is_scanned_through_its_import_graph(self):
        index = frontend_css_index()

        self.assertTrue(index["graph"])
        self.assertEqual(index["defined"]["maintenance-container"], {"app/MaintenanceMode/MaintenanceMode.css"})
        # SheetsDataTable is only reached through a lazily loaded route.
        self.assertNotIn("sdt-search", index["defined"])
        self.assertEqual(index["route"]["sdt-search"], {"components/SheetsDataTable/SheetsDataTable.css"})


class PageCssIndexTests(TestCase):
    def setUp(self):
        cache.clear()
        # Migration cms.0023 seeds the /acknowledgement page; start from no pages.
        CMSPage.objects.all().delete()

    def test_defined_scoped_and_hook_classes_per_route(self):
        CMSPage.objects.create(slug="landing", route="/landing", title="Landing", page_css=".promo {}\n.hero .cta {}")
        CMSPage.objects.create(slug="other", route="/other", title="Other", page_css=".promo:hover {}\n.promo.big {}")
        CMSPage.objects.create(slug="plain", route="/plain", title="Plain")

        index = page_css_index()

        self.assertEqual(set(index), {"defined", "scoped", "hook"})
        self.assertEqual(dict(index["defined"]), {"promo": {"/landing", "/other"}})
        # /other defines promo, so only big is listed as scoped there.
        self.assertEqual(dict(index["scoped"]), {"cta": {"/landing"}, "big": {"/other"}})
        self.assertEqual(dict(index["hook"]), {"hero": {"/landing"}})

    def test_no_page_css(self):
        CMSPage.objects.create(slug="plain", route="/plain", title="Plain")
        self.assertEqual(page_css_index(), EMPTY_MAPS)


class ContentClassUsageTests(TestCase):
    def setUp(self):
        cache.clear()
        CMSPage.objects.all().delete()
        FooterContent.objects.all().delete()
        self.zeta = CMSPage.objects.create(slug="zeta", route="/zeta", title="Zeta")
        self.alpha = CMSPage.objects.create(slug="alpha", route="/alpha", title="Alpha")

    def test_lists_every_block_page_wrapper_and_active_footer(self):
        CMSBlock.objects.create(
            page=self.zeta, block_type="rich_text", sort_order=0, data={"body_html": "<p class=wrap>z</p>"}
        )
        CMSBlock.objects.create(
            page=self.alpha,
            block_type="faq_list",
            sort_order=1,
            data={"items": [{"answer_html": '<p class="wrap wrap">a</p>'}]},
        )
        CMSBlock.objects.create(
            page=self.alpha, block_type="rich_text", sort_order=0, data={"body_html": "<b class='wrap'>b</b>"}
        )
        self.zeta.page_css_class = "wrap  wrap"
        self.zeta.save()
        FooterContent.objects.create(
            name="Main", slug="main", content={"contact_html": "<b class=wrap>x</b>"}, is_active=True
        )

        usage = content_class_usage()

        # Blocks by route then sort order, then page wrappers, then footers; one use per place.
        self.assertEqual(
            usage["wrap"],
            [
                {"source": "block:rich_text", "where": "/alpha"},
                {"source": "block:faq_list", "where": "/alpha"},
                {"source": "block:rich_text", "where": "/zeta"},
                {"source": "page_css_class", "where": "/zeta"},
                {"source": "footer", "where": "footer:main"},
            ],
        )

    def test_blocks_of_every_page_status_are_scanned(self):
        for status in ("published", "archived"):
            page = CMSPage.objects.create(slug=status, route=f"/{status}", title=status, status=status)
            CMSBlock.objects.create(page=page, block_type="rich_text", data={"body_html": "<p class=any>x</p>"})
        CMSBlock.objects.create(page=self.zeta, block_type="rich_text", data={"body_html": "<p class=any>x</p>"})

        self.assertEqual([use["where"] for use in content_class_usage()["any"]], ["/archived", "/published", "/zeta"])

    def test_page_css_class_splits_like_the_frontend_wrapper(self):
        # cmsPageClassName() splits on JavaScript's \s, which includes the no-break space.
        self.alpha.page_css_class = "one\u00a0two\tthree"
        self.alpha.save()

        usage = content_class_usage()

        self.assertEqual(set(usage), {"one", "two", "three"})
        self.assertEqual(usage["two"], [{"source": "page_css_class", "where": "/alpha"}])

    def test_footer_contact_and_column_html(self):
        FooterContent.objects.create(
            name="Main footer",
            slug="main",
            is_active=True,
            content={
                "contact_html": '<p class="footer-contact">UC Merced</p>',
                "columns": [{"title": "Links", "body_html": "<ul class=footer-list><li>x</li></ul>"}],
                "copyright": '<span class="not-html-key">c</span>',
            },
        )

        usage = content_class_usage()

        self.assertEqual(usage["footer-contact"], [{"source": "footer", "where": "footer:main"}])
        self.assertEqual(usage["footer-list"], [{"source": "footer", "where": "footer:main"}])
        self.assertNotIn("not-html-key", usage)

    def test_inactive_footers_are_not_scanned(self):
        FooterContent.objects.create(
            name="Old", slug="old", content={"contact_html": "<p class='shared only-old'>a</p>"}, is_active=False
        )
        FooterContent.objects.create(
            name="New", slug="new", content={"contact_html": "<p class=shared>b</p>"}, is_active=True
        )

        usage = content_class_usage()

        self.assertEqual(dict(usage), {"shared": [{"source": "footer", "where": "footer:new"}]})

    def test_no_active_footer_means_no_footer_uses(self):
        FooterContent.objects.create(name="Old", slug="old", content={"contact_html": "<p class=old>a</p>"})
        self.assertEqual(dict(content_class_usage()), {})

    def test_nothing_stored(self):
        self.assertEqual(dict(content_class_usage()), {})
