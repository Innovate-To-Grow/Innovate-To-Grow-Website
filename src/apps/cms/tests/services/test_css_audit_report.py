"""Tests for ``audit_css_classes`` and ``is_undefined`` in ``apps.cms.services.styles.audit`` (the report rows)."""

import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.cms.models import CMSBlock, CMSPage, FooterContent, StyleSheet
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
    "sheets",
    "inactive_sheets",
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
        self.assertFalse(is_undefined({"defined": False, "hook_in": ["sheet:events"]}))
        self.assertFalse(is_undefined({"defined": True, "hook_in": ["page_css:/x"]}))


class AuditCssClassesTests(TestCase):
    def setUp(self):
        cache.clear()
        StyleSheet.objects.all().delete()
        # Migration cms.0023 seeds the /acknowledgement page (with blocks); start from no pages.
        CMSPage.objects.all().delete()
        FooterContent.objects.all().delete()
        StyleSheet.objects.create(name="act", display_name="Active", css=".in-active { color: red; }", sort_order=1)
        StyleSheet.objects.create(
            name="old", display_name="Old", css=".in-inactive {}\n.in-active {}", sort_order=2, is_active=False
        )
        self.frontend = make_frontend_dir(self, ENTRY_AND_ROUTE_FRONTEND)
        self.audit_page = CMSPage.objects.create(slug="audit", route="/audit", title="Audit")
        self.other_page = CMSPage.objects.create(slug="other", route="/other", title="Other")
        CMSBlock.objects.create(
            page=self.audit_page,
            block_type="rich_text",
            sort_order=0,
            data={
                "heading": "Classes",
                "body_html": '<p class="in-active in-inactive">a</p><p class="in-frontend nowhere in-active">b</p>',
            },
        )
        CMSBlock.objects.create(
            page=self.other_page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<div class='in-active'>c</div>"},
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
        self.assertEqual(
            [row["class_name"] for row in report["classes"]], ["in-active", "in-frontend", "in-inactive", "nowhere"]
        )
        self.assertEqual(report["total_classes"], 4)
        # in-inactive (inactive sheet only) and nowhere.
        self.assertEqual(report["undefined_classes"], 2)
        self.assertEqual(report["undefined_classes"], sum(map(is_undefined, report["classes"])))
        for row in report["classes"]:
            with self.subTest(row=row["class_name"]):
                self.assertEqual(set(row), ROW_KEYS)
        json.dumps(report)  # The command prints the report as JSON.

    def test_class_in_an_active_sheet_is_defined(self):
        row = self._rows()["in-active"]

        self.assertTrue(row["defined"])
        self.assertEqual(row["sheets"], ["act"])
        self.assertEqual(row["inactive_sheets"], ["old"])
        self.assertEqual((row["frontend_files"], row["route_frontend_files"], row["page_css"]), ([], [], []))
        # One use per block, even when the block repeats the class.
        self.assertEqual(row["usage_count"], 2)
        self.assertEqual(row["pages"], ["/audit", "/other"])
        self.assertEqual(row["block_types"], ["rich_text"])
        self.assertEqual(row["sources"], ["block:rich_text"])
        self.assertEqual((row["footers"], row["scoped_in"], row["hook_in"]), ([], [], []))

    def test_class_only_in_an_inactive_sheet_is_undefined(self):
        row = self._rows()["in-inactive"]

        self.assertFalse(row["defined"])
        self.assertTrue(is_undefined(row))
        self.assertEqual(row["sheets"], [])
        self.assertEqual(row["inactive_sheets"], ["old"])
        self.assertEqual((row["usage_count"], row["pages"]), (1, ["/audit"]))

    def test_class_in_an_entry_bundle_file_is_defined(self):
        row = self._rows()["in-frontend"]

        self.assertTrue(row["defined"])
        self.assertEqual(row["frontend_files"], ["index.css"])
        self.assertEqual(row["route_frontend_files"], [])
        self.assertEqual((row["sheets"], row["inactive_sheets"]), ([], []))

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
                "sheets": [],
                "inactive_sheets": [],
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
        StyleSheet.objects.create(name="zeta", display_name="Zeta", css=".z .nowhere {}", sort_order=3)
        StyleSheet.objects.create(name="events", display_name="Events", css=".event-page .nowhere {}", sort_order=4)
        StyleSheet.objects.create(
            name="retired", display_name="Retired", css=".old-page .nowhere {}", sort_order=5, is_active=False
        )
        frontend = make_frontend_dir(
            self,
            {
                **ENTRY_AND_ROUTE_FRONTEND,
                "index.css": ".in-frontend {}\n.hero .nowhere {}",
                "routes/Lazy.css": ".route-only {}\n.lazy-page .nowhere {}",
            },
        )
        self._set_page(self.other_page, page_css=".wrap .nowhere {}")
        self._set_page(self.audit_page, page_css=".x > .nowhere {}")

        row = self._rows(frontend_dir=frontend)["nowhere"]

        self.assertFalse(row["defined"])
        self.assertEqual(
            (row["sheets"], row["frontend_files"], row["route_frontend_files"], row["page_css"]), ([], [], [], [])
        )
        # Active sheets (sorted), then frontend files (sorted), then page_css routes (sorted).
        # The inactive sheet is not served, so its scoped rule is not listed.
        self.assertEqual(
            row["scoped_in"],
            ["sheet:events", "sheet:zeta", "index.css", "routes/Lazy.css", "page_css:/audit", "page_css:/other"],
        )
        self.assertEqual(row["hook_in"], [])
        self.assertTrue(is_undefined(row))

    def test_hook_in_labels_and_order(self):
        # A page wrapper class nothing styles, but that rules hang on.
        self._set_page(self.audit_page, page_css_class="event-page", page_css=".event-page:hover .y {}")
        self._set_page(self.other_page, page_css=".event-page .x {}")
        StyleSheet.objects.create(name="zeta", display_name="Zeta", css=".event-page .a {}", sort_order=3)
        StyleSheet.objects.create(name="events", display_name="Events", css=".event-page > .b {}", sort_order=4)
        StyleSheet.objects.create(
            name="retired", display_name="Retired", css=".event-page .c {}", sort_order=5, is_active=False
        )
        frontend = make_frontend_dir(
            self,
            {
                **ENTRY_AND_ROUTE_FRONTEND,
                "index.css": ".in-frontend {}\n.event-page h1 {}",
                "routes/Lazy.css": ".route-only {}\n.event-page .lazy {}",
            },
        )

        report = self._report(frontend_dir=frontend)

        row = {row["class_name"]: row for row in report["classes"]}["event-page"]
        self.assertEqual(
            row["hook_in"],
            ["sheet:events", "sheet:zeta", "index.css", "routes/Lazy.css", "page_css:/audit", "page_css:/other"],
        )
        self.assertEqual((row["scoped_in"], row["sheets"], row["page_css"]), ([], [], []))
        self.assertEqual((row["sources"], row["pages"]), (["page_css_class"], ["/audit"]))
        # Not defined anywhere, but a hook: it does not count as undefined.
        self.assertFalse(row["defined"])
        self.assertFalse(is_undefined(row))
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (5, 2))

    def test_a_hook_in_an_inactive_sheet_still_counts_as_undefined(self):
        self._set_page(self.audit_page, page_css_class="wrap")
        StyleSheet.objects.create(name="gone", display_name="Gone", css=".wrap .x {}", sort_order=3, is_active=False)

        report = self._report()

        row = {row["class_name"]: row for row in report["classes"]}["wrap"]
        self.assertEqual((row["hook_in"], row["inactive_sheets"]), ([], []))
        self.assertTrue(is_undefined(row))
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (5, 3))

    def test_a_class_both_scoped_and_a_hook_lists_both(self):
        StyleSheet.objects.create(
            name="mixed", display_name="Mixed", css=".card .nowhere {}\n.nowhere .x {}", sort_order=3
        )

        report = self._report()

        row = {row["class_name"]: row for row in report["classes"]}["nowhere"]
        self.assertEqual((row["scoped_in"], row["hook_in"]), (["sheet:mixed"], ["sheet:mixed"]))
        self.assertFalse(is_undefined(row))
        self.assertEqual(report["undefined_classes"], 1)

    def test_class_both_defined_and_scoped_lists_both(self):
        StyleSheet.objects.create(name="events", display_name="Events", css=".event-page .in-active {}", sort_order=3)

        row = self._rows()["in-active"]

        self.assertTrue(row["defined"])
        self.assertEqual((row["sheets"], row["scoped_in"]), (["act"], ["sheet:events"]))

    def test_defined_means_an_active_sheet_or_an_entry_bundle_file(self):
        StyleSheet.objects.create(name="scoping", display_name="Scoping", css=".p .scoped-only {}", sort_order=3)
        self._set_page(self.audit_page, page_css=".page-only {}")
        self._add_block('<p class="route-only scoped-only page-only">x</p>')

        rows = self._rows()

        expected = {
            "in-active": True,  # active sheet
            "in-frontend": True,  # entry-bundle file
            "in-inactive": False,  # inactive sheet only
            "route-only": False,  # lazily loaded route file only
            "page-only": False,  # one page's page_css only
            "scoped-only": False,  # only inside another element
            "nowhere": False,
        }
        self.assertEqual({name: row["defined"] for name, row in rows.items()}, expected)
        report = self._report()
        self.assertEqual(report["undefined_classes"], 5)
        self.assertEqual(report["total_classes"], 7)

    def test_a_no_break_space_does_not_split_a_class(self):
        self._add_block('<p class="in-active&nbsp;nowhere">x</p>', page=self.other_page)

        rows = self._rows()

        self.assertIn("in-active nowhere", rows)
        self.assertTrue(is_undefined(rows["in-active nowhere"]))
        # The joined token is a different class: in-active and nowhere keep their own uses.
        self.assertEqual((rows["in-active"]["usage_count"], rows["nowhere"]["usage_count"]), (2, 1))

    def test_scan_frontend_false_reads_no_frontend_file(self):
        self._add_block('<p class="lazy-page">x</p>')

        with patch("apps.cms.services.styles.audit.frontend_css_index") as index:
            report = self._report(scan_frontend=False)

        index.assert_not_called()
        self.assertIs(report["frontend_scanned"], False)
        self.assertIsNone(report["frontend_dir"])
        self.assertIs(report["frontend_import_graph"], False)
        rows = {row["class_name"]: row for row in report["classes"]}
        row = rows["in-frontend"]
        self.assertEqual((row["frontend_files"], row["route_frontend_files"], row["scoped_in"]), ([], [], []))
        self.assertFalse(row["defined"])
        self.assertTrue(rows["in-active"]["defined"])
        # lazy-page hooks rules in routes/Lazy.css, which was not read.
        self.assertEqual(rows["lazy-page"]["hook_in"], [])
        self.assertEqual(report["undefined_classes"], 4)

    def test_frontend_hooks_count_when_the_frontend_is_scanned(self):
        self._add_block('<p class="lazy-page">x</p>')

        report = self._report()

        row = {row["class_name"]: row for row in report["classes"]}["lazy-page"]
        self.assertEqual(row["hook_in"], ["routes/Lazy.css"])
        self.assertFalse(is_undefined(row))
        self.assertEqual(report["undefined_classes"], 2)

    def test_missing_frontend_dir_reports_frontend_only_classes_as_undefined(self):
        missing = self.frontend / "no-such-dir"

        report = self._report(frontend_dir=missing)

        self.assertEqual((report["frontend_scanned"], report["frontend_dir"]), (True, str(missing)))
        self.assertIs(report["frontend_import_graph"], False)
        self.assertFalse({row["class_name"]: row for row in report["classes"]}["in-frontend"]["defined"])

    def test_default_frontend_dir_is_pages_src(self):
        report = audit_css_classes()

        self.assertEqual(report["frontend_dir"], str(default_frontend_dir()))
        self.assertIs(report["frontend_import_graph"], True)
        self.assertEqual(
            {row["class_name"] for row in report["classes"]}, {"in-active", "in-frontend", "in-inactive", "nowhere"}
        )

    def test_page_css_class_usage(self):
        self._set_page(self.other_page, page_css_class="landing  in-active")

        rows = self._rows()

        landing = rows["landing"]
        self.assertEqual((landing["usage_count"], landing["pages"], landing["footers"]), (1, ["/other"], []))
        self.assertEqual((landing["sources"], landing["block_types"]), (["page_css_class"], []))
        self.assertFalse(landing["defined"])
        in_active = rows["in-active"]
        self.assertEqual(in_active["usage_count"], 3)
        self.assertEqual(in_active["pages"], ["/audit", "/other"])
        self.assertEqual(in_active["sources"], ["block:rich_text", "page_css_class"])

    def test_footer_html_usage(self):
        FooterContent.objects.create(
            name="Main footer",
            slug="main",
            is_active=True,
            content={
                "contact_html": '<p class="footer-contact in-active">UC Merced</p>',
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
        in_active = rows["in-active"]
        self.assertEqual(in_active["usage_count"], 3)
        self.assertEqual((in_active["pages"], in_active["footers"]), (["/audit", "/other"], ["footer:main"]))
        self.assertEqual(in_active["sources"], ["block:rich_text", "footer"])

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
        self.assertEqual(report["total_classes"], 5)

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
