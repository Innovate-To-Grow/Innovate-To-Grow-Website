"""Tests for the ``audit_css_classes`` management command."""

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase

from apps.cms.models import CMSBlock, CMSPage, FooterContent

NO_FRONTEND_NOTICE = (
    "Frontend CSS not scanned, so no class reads as defined: this run reports usage only "
    "(which classes stored content uses, and where). Run it with the frontend sources (pages/src) "
    "to see what defines each class."
)
HEADER_RE = r"^class\s+uses\s+places\s+styled by$"


def no_graph_notice(frontend_dir):
    return f"No main.tsx in {frontend_dir}: every frontend CSS file counts as loaded on every page."


class _AuditCssClassesCommandCase(TestCase):
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


class AuditCssClassesCommandTests(_AuditCssClassesCommandCase):
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
