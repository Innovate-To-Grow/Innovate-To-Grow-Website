"""Tests for the ``audit_css_classes`` management command."""

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.cms.models import CMSBlock, CMSPage, FooterContent
from apps.cms.services.styles.audit import default_frontend_dir

NO_FRONTEND_NOTICE = (
    "Frontend CSS not scanned, so no class reads as defined: this run reports usage only "
    "(which classes stored content uses, and where). Run it with the frontend sources (pages/src) "
    "to see what defines each class."
)
HEADER_RE = r"^class\s+uses\s+places\s+styled by$"


def no_graph_notice(frontend_dir):
    return f"No main.tsx in {frontend_dir}: every frontend CSS file counts as loaded on every page."


class AuditCssClassesCommandTests(TestCase):
    def setUp(self):
        cache.clear()
        # Migration cms.0023 seeds the /acknowledgement page (with blocks); start from no pages.
        CMSPage.objects.all().delete()
        FooterContent.objects.all().delete()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.frontend = self.tmp / "src"
        self._write("main.tsx", "import './styles/x.css';\nconst R = React.lazy(() => import('./routes/Lazy'));\n")
        self._write("styles/x.css", ".fe {}\n.wrap .scoped-only {}")
        self._write("routes/Lazy.tsx", "import './Lazy.css';\n")
        self._write("routes/Lazy.css", ".lazy {}")
        self.page = CMSPage.objects.create(slug="audit", route="/audit", title="Audit")
        CMSBlock.objects.create(
            page=self.page,
            block_type="rich_text",
            data={"body_html": '<p class="fe nowhere scoped-only">x</p>'},
        )

    def _write(self, relative, text):
        path = self.frontend / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _run(self, *args):
        out, err = StringIO(), StringIO()
        call_command("audit_css_classes", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def _out(self, *args):
        return self._run(*args)[0]

    def test_table_output(self):
        out, err = self._run("--frontend-dir", str(self.frontend))

        lines = out.splitlines()
        self.assertRegex(lines[0], HEADER_RE)
        self.assertEqual(len(lines), 5)
        self.assertRegex(lines[1], r"^fe\s+1\s+1\s+styles/x\.css$")
        self.assertRegex(lines[2], r"^nowhere\s+1\s+1\s+NOWHERE$")
        self.assertRegex(lines[3], r"^scoped-only\s+1\s+1\s+scoped:styles/x\.css$")
        self.assertEqual(lines[4], "3 class(es) used in stored CMS content, 2 with no site-wide definition.")
        self.assertEqual(err, "")

    def test_places_column_counts_pages_and_footers(self):
        CMSPage.objects.create(slug="other", route="/other", title="Other", page_css_class="fe")
        CMSBlock.objects.create(
            page=self.page, block_type="rich_text", sort_order=1, data={"body_html": "<a class=fe>go</a>"}
        )
        FooterContent.objects.create(
            name="Old", slug="old", content={"contact_html": "<p class='fe'>x</p>"}, is_active=False
        )
        FooterContent.objects.create(
            name="Main", slug="main", content={"contact_html": "<p class='fe'>x</p>"}, is_active=True
        )

        out = self._out("--frontend-dir", str(self.frontend))

        # 2 blocks on /audit + /other's page_css_class + the active footer = 4 uses in 3 places.
        # The inactive footer is not served, so it is neither a use nor a place.
        self.assertRegex(out, r"(?m)^fe\s+4\s+3\s+styles/x\.css$")

    def test_styled_by_column_lists_every_label_in_order(self):
        self._write(
            "main.tsx",
            "import './styles/x.css';\nimport './styles/a.css';\nconst R = React.lazy(() => import('./routes/Lazy'));\n",
        )
        # x.css both defines and scopes it: a file that defines a class is not listed as scoping it.
        self._write("styles/x.css", ".fe {}\n.card .fe {}")
        self._write("styles/a.css", ".fe:hover {}")
        self._write("styles/y.css", ".hero .fe {}")
        self._write("routes/Lazy.css", ".lazy {}\n.fe {}")
        self._write("styles/z.css", ".fe .inner {}")

        out = self._out("--frontend-dir", str(self.frontend))

        # Entry-bundle files, route-only, scoped, hook; each group sorted.
        self.assertRegex(
            out,
            r"(?m)^fe\s+1\s+1\s+styles/a\.css, styles/x\.css, route-only:routes/Lazy\.css, "
            r"scoped:styles/y\.css, hook:styles/z\.css$",
        )

    def test_hook_label_lists_css_that_hangs_rules_on_a_class(self):
        # A page wrapper class: nothing styles it, but frontend files style elements inside it.
        self.page.page_css_class = "wrap"
        self.page.save()
        self._write("routes/Lazy.css", ".lazy {}\n.wrap a {}")

        out = self._out("--frontend-dir", str(self.frontend))

        self.assertRegex(out, r"(?m)^wrap\s+1\s+1\s+hook:routes/Lazy\.css,styles/x\.css$")
        # A hook is not counted as missing a definition.
        self.assertIn("4 class(es) used in stored CMS content, 2 with no site-wide definition.", out)

    def test_hook_label_follows_the_other_labels(self):
        self._write("styles/x.css", ".fe {}\n.wrap .scoped-only {}\n.card .nowhere {}\n.nowhere .x {}")

        out = self._out("--frontend-dir", str(self.frontend))

        self.assertRegex(out, r"(?m)^nowhere\s+1\s+1\s+scoped:styles/x\.css, hook:styles/x\.css$")
        # Scoped and hooked: still a hook, so no longer undefined.
        self.assertIn("3 class(es) used in stored CMS content, 1 with no site-wide definition.", out)

    def test_undefined_only_leaves_out_hooks(self):
        self.page.page_css_class = "wrap"
        self.page.save()

        out = self._out("--frontend-dir", str(self.frontend), "--undefined-only")

        lines = out.splitlines()
        self.assertEqual([line.split()[0] for line in lines[1:-1]], ["nowhere", "scoped-only"])
        self.assertNotIn("hook:", out)
        self.assertEqual(lines[-1], "Showing the 2 undefined of 4 class(es) used in stored CMS content.")
        report = json.loads(self._out("--frontend-dir", str(self.frontend), "--undefined-only", "--json"))
        self.assertNotIn("wrap", [row["class_name"] for row in report["classes"]])
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (4, 2))

    def test_route_only_label_for_css_loaded_by_a_lazy_route(self):
        CMSBlock.objects.create(
            page=self.page, block_type="rich_text", sort_order=1, data={"body_html": '<p class="lazy">x</p>'}
        )

        out = self._out("--frontend-dir", str(self.frontend))

        self.assertRegex(out, r"(?m)^lazy\s+1\s+1\s+route-only:routes/Lazy\.css$")
        # A route-only class has no site-wide definition.
        self.assertIn("4 class(es) used in stored CMS content, 3 with no site-wide definition.", out)

    def test_undefined_only_lists_classes_with_no_site_wide_definition(self):
        out = self._out("--frontend-dir", str(self.frontend), "--undefined-only")

        lines = out.splitlines()
        self.assertRegex(lines[0], HEADER_RE)
        # A scoped-only class counts as undefined.
        self.assertEqual([line.split()[0] for line in lines[1:-1]], ["nowhere", "scoped-only"])
        self.assertNotRegex(out, r"(?m)^fe\s")
        self.assertEqual(lines[-1], "Showing the 2 undefined of 3 class(es) used in stored CMS content.")

    def test_undefined_only_without_frontend_includes_frontend_only_classes(self):
        report = json.loads(self._out("--no-frontend", "--undefined-only", "--json"))

        self.assertEqual([row["class_name"] for row in report["classes"]], ["fe", "nowhere", "scoped-only"])
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (3, 3))

    def test_json_output_is_the_whole_report(self):
        out, err = self._run("--frontend-dir", str(self.frontend), "--json")

        report = json.loads(out)
        self.assertEqual(
            set(report),
            {
                "frontend_scanned",
                "frontend_dir",
                "frontend_import_graph",
                "total_classes",
                "undefined_classes",
                "classes",
            },
        )
        self.assertIs(report["frontend_scanned"], True)
        self.assertEqual(report["frontend_dir"], str(self.frontend))
        self.assertIs(report["frontend_import_graph"], True)
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (3, 2))
        rows = report["classes"]
        self.assertEqual([row["class_name"] for row in rows], ["fe", "nowhere", "scoped-only"])
        by_name = {row["class_name"]: row for row in rows}
        self.assertEqual(by_name["fe"]["frontend_files"], ["styles/x.css"])
        self.assertTrue(by_name["fe"]["defined"])
        self.assertEqual(by_name["scoped-only"]["scoped_in"], ["styles/x.css"])
        self.assertFalse(by_name["scoped-only"]["defined"])
        self.assertFalse(by_name["nowhere"]["defined"])
        self.assertEqual(by_name["nowhere"]["pages"], ["/audit"])
        self.assertEqual(by_name["nowhere"]["footers"], [])
        self.assertEqual(by_name["nowhere"]["sources"], ["block:rich_text"])
        self.assertEqual(by_name["nowhere"]["route_frontend_files"], [])
        self.assertEqual(err, "")

    def test_json_with_undefined_only_filters_rows_but_not_totals(self):
        report = json.loads(self._out("--frontend-dir", str(self.frontend), "--json", "--undefined-only"))

        self.assertEqual([row["class_name"] for row in report["classes"]], ["nowhere", "scoped-only"])
        self.assertEqual((report["total_classes"], report["undefined_classes"]), (3, 2))

    def test_no_content_reports_zero_classes(self):
        CMSBlock.objects.all().delete()

        report = json.loads(self._out("--frontend-dir", str(self.frontend), "--json"))
        self.assertEqual((report["classes"], report["total_classes"], report["undefined_classes"]), ([], 0, 0))

        out = self._out("--frontend-dir", str(self.frontend))
        self.assertRegex(out.splitlines()[0], HEADER_RE)
        self.assertEqual(out.splitlines()[1], "0 class(es) used in stored CMS content, 0 with no site-wide definition.")
        self.assertIn(
            "Showing the 0 undefined of 0 class(es) used in stored CMS content.",
            self._out("--frontend-dir", str(self.frontend), "--undefined-only"),
        )

    def test_default_frontend_dir_is_scanned_without_a_notice(self):
        out, err = self._run("--undefined-only")

        # The real pages/src does not define this made-up class, so it stays undefined.
        self.assertRegex(out, r"(?m)^nowhere\s+1\s+1\s+NOWHERE$")
        self.assertEqual(err, "")
        report = json.loads(self._out("--json"))
        self.assertEqual(report["frontend_dir"], str(default_frontend_dir()))
        self.assertIs(report["frontend_import_graph"], True)

    def test_frontend_dir_without_main_tsx_writes_a_notice(self):
        (self.frontend / "main.tsx").unlink()
        CMSBlock.objects.create(
            page=self.page, block_type="rich_text", sort_order=1, data={"body_html": '<p class="lazy">x</p>'}
        )

        out, err = self._run("--frontend-dir", str(self.frontend))

        self.assertEqual(err.strip(), no_graph_notice(self.frontend))
        # Without the import graph the lazy route's file counts as loaded on every page.
        self.assertRegex(out, r"(?m)^lazy\s+1\s+1\s+routes/Lazy\.css$")
        self.assertRegex(out, r"(?m)^fe\s+1\s+1\s+styles/x\.css$")
        self.assertIn("4 class(es) used in stored CMS content, 2 with no site-wide definition.", out)

        out, err = self._run("--frontend-dir", str(self.frontend), "--json")
        self.assertIs(json.loads(out)["frontend_import_graph"], False)
        self.assertEqual(err.strip(), no_graph_notice(self.frontend))

    def test_missing_frontend_dir_is_an_error(self):
        missing = self.tmp / "no-such-src"
        out, err = StringIO(), StringIO()

        with self.assertRaises(CommandError) as caught:
            call_command("audit_css_classes", "--frontend-dir", str(missing), stdout=out, stderr=err)

        self.assertEqual(
            str(caught.exception),
            f"Frontend CSS directory not found: {missing}. "
            "Pass --frontend-dir PATH, or --no-frontend to report usage only.",
        )
        self.assertEqual(caught.exception.returncode, 1)
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))

    def test_frontend_dir_that_is_a_file_is_an_error(self):
        not_a_dir = self.frontend / "styles" / "x.css"

        with self.assertRaisesMessage(CommandError, f"Frontend CSS directory not found: {not_a_dir}."):
            self._run("--frontend-dir", str(not_a_dir))

    def test_missing_default_frontend_dir_is_an_error(self):
        # A server image without pages/src.
        missing = self.tmp / "pages" / "src"
        with patch("apps.cms.management.commands.audit_css_classes.default_frontend_dir", return_value=missing):
            with self.assertRaisesMessage(CommandError, f"Frontend CSS directory not found: {missing}."):
                self._run()

    def test_no_frontend_writes_a_notice_and_does_not_fail(self):
        missing = self.tmp / "pages" / "src"
        with patch("apps.cms.management.commands.audit_css_classes.default_frontend_dir", return_value=missing):
            out, err = self._run("--no-frontend")

        self.assertEqual(err.strip(), NO_FRONTEND_NOTICE)
        # Frontend CSS was not read: fe and scoped-only are styled only there.
        self.assertRegex(out, r"(?m)^fe\s+1\s+1\s+NOWHERE$")
        self.assertRegex(out, r"(?m)^scoped-only\s+1\s+1\s+NOWHERE$")
        self.assertRegex(out, r"(?m)^nowhere\s+1\s+1\s+NOWHERE$")
        self.assertIn("3 class(es) used in stored CMS content, 3 with no site-wide definition.", out)

    def test_no_frontend_ignores_a_given_frontend_dir(self):
        out, err = self._run("--no-frontend", "--frontend-dir", str(self.tmp / "missing"))

        self.assertEqual(err.strip(), NO_FRONTEND_NOTICE)
        self.assertRegex(out, r"(?m)^fe\s+1\s+1\s+NOWHERE$")

        out, err = self._run("--no-frontend", "--frontend-dir", str(self.frontend), "--json")
        report = json.loads(out)
        self.assertEqual(
            (report["frontend_scanned"], report["frontend_dir"], report["frontend_import_graph"]), (False, None, False)
        )
        by_name = {row["class_name"]: row for row in report["classes"]}
        self.assertEqual((by_name["fe"]["frontend_files"], by_name["fe"]["defined"]), ([], False))
        self.assertEqual(err.strip(), NO_FRONTEND_NOTICE)
