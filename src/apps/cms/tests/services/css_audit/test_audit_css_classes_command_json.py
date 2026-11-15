import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError

from apps.cms.models import CMSBlock
from apps.cms.services.styles.audit import default_frontend_dir
from apps.cms.tests.services.css_audit.test_audit_css_classes_command import (
    HEADER_RE,
    NO_FRONTEND_NOTICE,
    _AuditCssClassesCommandCase,
    no_graph_notice,
)


class AuditCssClassesCommandTests(_AuditCssClassesCommandCase):
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
