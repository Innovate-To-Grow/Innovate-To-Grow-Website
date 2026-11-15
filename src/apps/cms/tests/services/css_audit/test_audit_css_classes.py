import json

from django.core.cache import cache
from django.test import TestCase

from apps.cms.models import CMSBlock, CMSPage, FooterContent
from apps.cms.services.styles.audit import audit_css_classes, is_undefined
from apps.cms.tests.services.css_audit.test_css_audit import ENTRY_AND_ROUTE_FRONTEND, make_frontend_dir
from apps.cms.tests.services.css_audit.test_css_audit_report import REPORT_KEYS, ROW_KEYS


class _AuditCssClassesCase(TestCase):
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


class AuditCssClassesTests(_AuditCssClassesCase):
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
        self.assertEqual(row["route_frontend_files"], [])
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

        row = self._rows(frontend_dir=frontend)["nowhere"]

        self.assertFalse(row["defined"])
        self.assertEqual((row["frontend_files"], row["route_frontend_files"]), ([], []))
        # Frontend files, sorted, entry and route alike.
        self.assertEqual(row["scoped_in"], ["features/Card.css", "index.css", "routes/Lazy.css"])
        self.assertEqual(row["hook_in"], [])
        self.assertTrue(is_undefined(row))
