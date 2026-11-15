from unittest.mock import patch

from apps.cms.models import FooterContent
from apps.cms.services.styles.audit import audit_css_classes, default_frontend_dir, is_undefined
from apps.cms.tests.services.css_audit.test_audit_css_classes import _AuditCssClassesCase
from apps.cms.tests.services.css_audit.test_css_audit import ENTRY_AND_ROUTE_FRONTEND, make_frontend_dir


class AuditCssClassesTests(_AuditCssClassesCase):
    def test_hook_in_labels_and_order(self):
        # A page wrapper class nothing styles, but that rules hang on.
        self._set_page(self.audit_page, page_css_class="event-page")
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
        self.assertEqual(row["hook_in"], ["features/Card.css", "index.css", "routes/Lazy.css"])
        self.assertEqual((row["scoped_in"], row["frontend_files"]), ([], []))
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
        frontend = make_frontend_dir(
            self, {**ENTRY_AND_ROUTE_FRONTEND, "features/Card.css": ".event-page .in-frontend {}"}
        )

        row = self._rows(frontend_dir=frontend)["in-frontend"]

        self.assertTrue(row["defined"])
        self.assertEqual((row["frontend_files"], row["scoped_in"]), (["index.css"], ["features/Card.css"]))

    def test_defined_means_an_entry_bundle_file(self):
        frontend = make_frontend_dir(
            self, {**ENTRY_AND_ROUTE_FRONTEND, "index.css": ".in-frontend {}\n.p .scoped-only {}"}
        )
        self._add_block('<p class="route-only scoped-only">x</p>')

        report = self._report(frontend_dir=frontend)

        expected = {
            "in-frontend": True,  # entry-bundle file
            "route-only": False,  # lazily loaded route file only
            "scoped-only": False,  # only inside another element, even in an entry-bundle file
            "nowhere": False,
        }
        self.assertEqual({row["class_name"]: row["defined"] for row in report["classes"]}, expected)
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (4, 3))

    def test_a_no_break_space_does_not_split_a_class(self):
        self._add_block('<p class="in-frontend&nbsp;nowhere">x</p>', page=self.other_page)

        rows = self._rows()

        self.assertIn("in-frontend nowhere", rows)
        self.assertTrue(is_undefined(rows["in-frontend nowhere"]))
        # The joined token is a different class: in-frontend and nowhere keep their own uses.
        self.assertEqual((rows["in-frontend"]["usage_count"], rows["nowhere"]["usage_count"]), (2, 1))

    def test_scan_frontend_false_reads_no_frontend_file(self):
        self._add_block('<p class="lazy-page">x</p>')

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
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (3, 3))

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
