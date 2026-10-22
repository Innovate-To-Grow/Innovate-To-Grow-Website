"""Tests for ``audit_css_classes`` and ``is_undefined`` in ``apps.cms.services.styles.audit`` (the report rows)."""

import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.cms.models import CMSBlock, CMSPage, FooterContent
from apps.cms.services.styles.audit import audit_css_classes, default_frontend_dir, is_undefined
from apps.cms.tests.services.test_css_audit import ENTRY_AND_ROUTE_FRONTEND, make_frontend_dir

REPORT_KEYS = {
    "frontend_scanned",
    "frontend_dir",
    "frontend_import_graph",
    "total_classes",
    "undefined_classes",
    "classes",
}
ROW_KEYS = {
    "class_name",
    "usage_count",
    "pages",
    "footers",
    "sources",
    "block_types",
    "frontend_files",
    "route_frontend_files",
    "page_css",
    "scoped_in",
    "hook_in",
    "defined",
}


class IsUndefinedTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_undefined_means_no_site_wide_definition_and_no_hook(self):
        self.assertTrue(is_undefined({"defined": False, "hook_in": []}))
        self.assertFalse(is_undefined({"defined": True, "hook_in": []}))
        self.assertFalse(is_undefined({"defined": False, "hook_in": ["styles/events.css"]}))
        self.assertFalse(is_undefined({"defined": True, "hook_in": ["page_css:/x"]}))


class AuditCssClassesTests(TestCase):
    def setUp(self):
        cache.clear()
        # Migration cms.0023 seeds the /acknowledgement page (with blocks); start from no pages.
        CMSPage.objects.all().delete()
        FooterContent.objects.all().delete()
        self.frontend = make_frontend_dir(self, ENTRY_AND_ROUTE_FRONTEND)
        self.audit_page = CMSPage.objects.create(slug="audit", route="/audit", title="Audit")
        self.other_page = CMSPage.objects.create(slug="other", route="/other", title="Other")
        CMSBlock.objects.create(
            page=self.audit_page,
            block_type="rich_text",
            sort_order=0,
            data={
                "heading": "Classes",
                "body_html": '<p class="in-frontend">a</p><p class="nowhere in-frontend">b</p>',
            },
        )
        CMSBlock.objects.create(
            page=self.other_page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<div class='in-frontend'>c</div>"},
        )

    def _report(self, **kwargs):
        kwargs.setdefault("frontend_dir", self.frontend)
        return audit_css_classes(**kwargs)

    def _rows(self, **kwargs):
        return {row["class_name"]: row for row in self._report(**kwargs)["classes"]}

    def _add_block(self, html, *, page=None, block_type="rich_text", sort_order=5):
        CMSBlock.objects.create(
            page=page or self.audit_page, block_type=block_type, sort_order=sort_order, data={"body_html": html}
        )

    def _set_page(self, page, **fields):
        for name, value in fields.items():
            setattr(page, name, value)
        page.save()

    def test_report_shape_and_totals(self):
        report = self._report()

        self.assertEqual(set(report), REPORT_KEYS)
        self.assertIs(report["frontend_scanned"], True)
        self.assertEqual(report["frontend_dir"], str(self.frontend))
        self.assertIs(report["frontend_import_graph"], True)
        self.assertEqual([row["class_name"] for row in report["classes"]], ["in-frontend", "nowhere"])
        self.assertEqual(report["total_classes"], 2)
        self.assertEqual(report["undefined_classes"], 1)
        self.assertEqual(report["undefined_classes"], sum(map(is_undefined, report["classes"])))
        for row in report["classes"]:
            with self.subTest(row=row["class_name"]):
                self.assertEqual(set(row), ROW_KEYS)
        json.dumps(report)  # The command prints the report as JSON.

    def test_class_in_an_entry_bundle_file_is_defined(self):
        row = self._rows()["in-frontend"]

        self.assertTrue(row["defined"])
        self.assertFalse(is_undefined(row))
        self.assertEqual(row["frontend_files"], ["index.css"])
        self.assertEqual((row["route_frontend_files"], row["page_css"]), ([], []))
        # One use per block, even when the block repeats the class.
        self.assertEqual(row["usage_count"], 2)
        self.assertEqual(row["pages"], ["/audit", "/other"])
        self.assertEqual(row["block_types"], ["rich_text"])
        self.assertEqual(row["sources"], ["block:rich_text"])
        self.assertEqual((row["footers"], row["scoped_in"], row["hook_in"]), ([], [], []))

    def test_class_defined_nowhere(self):
        self.assertEqual(
            self._rows()["nowhere"],
            {
                "class_name": "nowhere",
                "usage_count": 1,
                "pages": ["/audit"],
                "footers": [],
                "sources": ["block:rich_text"],
                "block_types": ["rich_text"],
                "frontend_files": [],
                "route_frontend_files": [],
                "page_css": [],
                "scoped_in": [],
                "hook_in": [],
                "defined": False,
            },
        )

    def test_class_only_in_a_lazy_route_file_is_not_defined(self):
        self._add_block('<p class="route-only route-scoped">r</p>')

        rows = self._rows()

        route_only = rows["route-only"]
        self.assertFalse(route_only["defined"])
        self.assertTrue(is_undefined(route_only))
        self.assertEqual((route_only["frontend_files"], route_only["route_frontend_files"]), ([], ["routes/Lazy.css"]))
        self.assertEqual(route_only["scoped_in"], [])
        route_scoped = rows["route-scoped"]
        self.assertFalse(route_scoped["defined"])
        self.assertEqual((route_scoped["route_frontend_files"], route_scoped["scoped_in"]), ([], ["routes/Lazy.css"]))

    def test_class_in_an_entry_and_a_route_file_lists_both(self):
        frontend = make_frontend_dir(
            self, {**ENTRY_AND_ROUTE_FRONTEND, "routes/Lazy.css": ".in-frontend { margin: 0; }"}
        )

        row = self._rows(frontend_dir=frontend)["in-frontend"]

        self.assertTrue(row["defined"])
        self.assertEqual((row["frontend_files"], row["route_frontend_files"]), (["index.css"], ["routes/Lazy.css"]))

    def test_frontend_dir_without_main_tsx_counts_every_file_as_entry(self):
        files = {key: value for key, value in ENTRY_AND_ROUTE_FRONTEND.items() if key != "main.tsx"}
        frontend = make_frontend_dir(self, files)
        self._add_block('<p class="route-only">r</p>')

        report = self._report(frontend_dir=frontend)

        self.assertIs(report["frontend_import_graph"], False)
        row = {row["class_name"]: row for row in report["classes"]}["route-only"]
        self.assertTrue(row["defined"])
        self.assertEqual((row["frontend_files"], row["route_frontend_files"]), (["routes/Lazy.css"], []))

    def test_page_css_defines_a_class_for_its_route_only(self):
        self._set_page(self.audit_page, page_css=".promo { color: red; }")
        self._set_page(self.other_page, page_css=".landing .promo { }")
        self._add_block('<p class="promo">p</p>', page=self.other_page)

        row = self._rows()["promo"]

        self.assertFalse(row["defined"])
        self.assertTrue(is_undefined(row))
        self.assertEqual(row["page_css"], ["/audit"])
        self.assertEqual(row["scoped_in"], ["page_css:/other"])
        self.assertEqual(row["pages"], ["/other"])

    def test_scoped_in_labels_and_order(self):
        frontend = make_frontend_dir(
            self,
            {
                **ENTRY_AND_ROUTE_FRONTEND,
                "index.css": ".in-frontend {}\n.hero .nowhere {}",
                "routes/Lazy.css": ".route-only {}\n.lazy-page .nowhere {}",
                "features/Card.css": ".card .nowhere {}",
            },
        )
        self._set_page(self.other_page, page_css=".wrap .nowhere {}")
        self._set_page(self.audit_page, page_css=".x > .nowhere {}")

        row = self._rows(frontend_dir=frontend)["nowhere"]

        self.assertFalse(row["defined"])
        self.assertEqual((row["frontend_files"], row["route_frontend_files"], row["page_css"]), ([], [], []))
        # Frontend files (sorted, entry and route alike), then page_css routes (sorted).
        self.assertEqual(
            row["scoped_in"],
            ["features/Card.css", "index.css", "routes/Lazy.css", "page_css:/audit", "page_css:/other"],
        )
        self.assertEqual(row["hook_in"], [])
        self.assertTrue(is_undefined(row))

    def test_hook_in_labels_and_order(self):
        # A page wrapper class nothing styles, but that rules hang on.
        self._set_page(self.audit_page, page_css_class="event-page", page_css=".event-page:hover .y {}")
        self._set_page(self.other_page, page_css=".event-page .x {}")
        frontend = make_frontend_dir(
            self,
            {
                **ENTRY_AND_ROUTE_FRONTEND,
                "index.css": ".in-frontend {}\n.event-page h1 {}",
                "routes/Lazy.css": ".route-only {}\n.event-page .lazy {}",
                "features/Card.css": ".event-page > .card {}",
            },
        )

        report = self._report(frontend_dir=frontend)

        row = {row["class_name"]: row for row in report["classes"]}["event-page"]
        self.assertEqual(
            row["hook_in"],
            ["features/Card.css", "index.css", "routes/Lazy.css", "page_css:/audit", "page_css:/other"],
        )
        self.assertEqual((row["scoped_in"], row["frontend_files"], row["page_css"]), ([], [], []))
        self.assertEqual((row["sources"], row["pages"]), (["page_css_class"], ["/audit"]))
        # Not defined anywhere, but a hook: it does not count as undefined.
        self.assertFalse(row["defined"])
        self.assertFalse(is_undefined(row))
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (3, 1))

    def test_a_class_both_scoped_and_a_hook_lists_both(self):
        frontend = make_frontend_dir(
            self, {**ENTRY_AND_ROUTE_FRONTEND, "index.css": ".in-frontend {}\n.card .nowhere {}\n.nowhere .x {}"}
        )

        report = self._report(frontend_dir=frontend)

        row = {row["class_name"]: row for row in report["classes"]}["nowhere"]
        self.assertEqual((row["scoped_in"], row["hook_in"]), (["index.css"], ["index.css"]))
        self.assertFalse(row["defined"])
        self.assertFalse(is_undefined(row))
        self.assertEqual(report["undefined_classes"], 0)

    def test_class_both_defined_and_scoped_lists_both(self):
        self._set_page(self.other_page, page_css=".event-page .in-frontend {}")

        row = self._rows()["in-frontend"]

        self.assertTrue(row["defined"])
        self.assertEqual((row["frontend_files"], row["scoped_in"]), (["index.css"], ["page_css:/other"]))

    def test_defined_means_an_entry_bundle_file(self):
        frontend = make_frontend_dir(
            self, {**ENTRY_AND_ROUTE_FRONTEND, "index.css": ".in-frontend {}\n.p .scoped-only {}"}
        )
        self._set_page(self.audit_page, page_css=".page-only {}")
        self._add_block('<p class="route-only scoped-only page-only">x</p>')

        report = self._report(frontend_dir=frontend)

        expected = {
            "in-frontend": True,  # entry-bundle file
            "route-only": False,  # lazily loaded route file only
            "page-only": False,  # one page's page_css only
            "scoped-only": False,  # only inside another element, even in an entry-bundle file
            "nowhere": False,
        }
        self.assertEqual({row["class_name"]: row["defined"] for row in report["classes"]}, expected)
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (5, 4))

    def test_a_no_break_space_does_not_split_a_class(self):
        self._add_block('<p class="in-frontend&nbsp;nowhere">x</p>', page=self.other_page)

        rows = self._rows()

        self.assertIn("in-frontend nowhere", rows)
        self.assertTrue(is_undefined(rows["in-frontend nowhere"]))
        # The joined token is a different class: in-frontend and nowhere keep their own uses.
        self.assertEqual((rows["in-frontend"]["usage_count"], rows["nowhere"]["usage_count"]), (2, 1))

    def test_scan_frontend_false_reads_no_frontend_file(self):
        self._set_page(self.other_page, page_css=".promo {}\n.wrap .y {}")
        self._add_block('<p class="lazy-page promo wrap">x</p>')

        with patch("apps.cms.services.styles.audit.frontend_css_index") as index:
            report = self._report(scan_frontend=False)

        index.assert_not_called()
        self.assertIs(report["frontend_scanned"], False)
        self.assertIsNone(report["frontend_dir"])
        self.assertIs(report["frontend_import_graph"], False)
        rows = {row["class_name"]: row for row in report["classes"]}
        # Usage only: no class reads as defined, but where each one is used is still reported.
        self.assertEqual([name for name, row in rows.items() if row["defined"]], [])
        row = rows["in-frontend"]
        self.assertEqual((row["frontend_files"], row["route_frontend_files"], row["scoped_in"]), ([], [], []))
        self.assertEqual((row["usage_count"], row["pages"]), (2, ["/audit", "/other"]))
        # lazy-page hooks rules in routes/Lazy.css, which was not read.
        self.assertEqual(rows["lazy-page"]["hook_in"], [])
        # Page CSS lives in the database, so it is still read.
        self.assertEqual(rows["promo"]["page_css"], ["/other"])
        self.assertEqual(rows["wrap"]["hook_in"], ["page_css:/other"])
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (5, 4))

    def test_frontend_hooks_count_when_the_frontend_is_scanned(self):
        self._add_block('<p class="lazy-page">x</p>')

        report = self._report()

        row = {row["class_name"]: row for row in report["classes"]}["lazy-page"]
        self.assertEqual(row["hook_in"], ["routes/Lazy.css"])
        self.assertFalse(is_undefined(row))
        self.assertEqual(report["undefined_classes"], 1)

    def test_missing_frontend_dir_reports_frontend_only_classes_as_undefined(self):
        missing = self.frontend / "no-such-dir"

        report = self._report(frontend_dir=missing)

        self.assertEqual((report["frontend_scanned"], report["frontend_dir"]), (True, str(missing)))
        self.assertIs(report["frontend_import_graph"], False)
        self.assertFalse({row["class_name"]: row for row in report["classes"]}["in-frontend"]["defined"])
        self.assertEqual(report["undefined_classes"], 2)

    def test_default_frontend_dir_is_pages_src(self):
        report = audit_css_classes()

        self.assertEqual(report["frontend_dir"], str(default_frontend_dir()))
        self.assertIs(report["frontend_import_graph"], True)
        self.assertEqual({row["class_name"] for row in report["classes"]}, {"in-frontend", "nowhere"})

    def test_page_css_class_usage(self):
        self._set_page(self.other_page, page_css_class="landing  in-frontend")

        rows = self._rows()

        landing = rows["landing"]
        self.assertEqual((landing["usage_count"], landing["pages"], landing["footers"]), (1, ["/other"], []))
        self.assertEqual((landing["sources"], landing["block_types"]), (["page_css_class"], []))
        self.assertFalse(landing["defined"])
        in_frontend = rows["in-frontend"]
        self.assertEqual(in_frontend["usage_count"], 3)
        self.assertEqual(in_frontend["pages"], ["/audit", "/other"])
        self.assertEqual(in_frontend["sources"], ["block:rich_text", "page_css_class"])

    def test_footer_html_usage(self):
        FooterContent.objects.create(
            name="Main footer",
            slug="main",
            is_active=True,
            content={
                "contact_html": '<p class="footer-contact in-frontend">UC Merced</p>',
                "columns": [{"title": "Links", "body_html": "<ul class=footer-list><li>x</li></ul>"}],
                "copyright": '<span class="not-html-key">c</span>',
            },
        )

        rows = self._rows()

        contact = rows["footer-contact"]
        self.assertEqual((contact["usage_count"], contact["pages"], contact["footers"]), (1, [], ["footer:main"]))
        self.assertEqual((contact["sources"], contact["block_types"]), (["footer"], []))
        self.assertEqual((rows["footer-list"]["footers"], rows["footer-list"]["pages"]), (["footer:main"], []))
        self.assertNotIn("not-html-key", rows)
        in_frontend = rows["in-frontend"]
        self.assertEqual(in_frontend["usage_count"], 3)
        self.assertEqual((in_frontend["pages"], in_frontend["footers"]), (["/audit", "/other"], ["footer:main"]))
        self.assertEqual(in_frontend["sources"], ["block:rich_text", "footer"])

    def test_only_the_active_footer_is_scanned(self):
        FooterContent.objects.create(
            name="Old", slug="old", content={"contact_html": "<p class='shared only-old'>a</p>"}, is_active=False
        )
        FooterContent.objects.create(
            name="New", slug="new", content={"contact_html": "<p class=shared>b</p>"}, is_active=True
        )

        report = self._report()

        rows = {row["class_name"]: row for row in report["classes"]}
        self.assertEqual((rows["shared"]["usage_count"], rows["shared"]["footers"]), (1, ["footer:new"]))
        self.assertNotIn("only-old", rows)
        self.assertEqual(report["total_classes"], 3)

    def test_nested_html_fields_of_other_block_types_are_scanned(self):
        CMSBlock.objects.create(
            page=self.other_page,
            block_type="faq_list",
            sort_order=1,
            data={"items": [{"question": "Q", "answer_html": '<p class="faq-answer">A</p>'}]},
        )

        row = self._rows()["faq-answer"]

        self.assertEqual((row["pages"], row["block_types"], row["defined"]), (["/other"], ["faq_list"], False))
        self.assertEqual(row["sources"], ["block:faq_list"])

    def test_no_content_means_no_rows(self):
        CMSBlock.objects.all().delete()

        report = self._report()

        self.assertEqual((report["classes"], report["total_classes"], report["undefined_classes"]), ([], 0, 0))
