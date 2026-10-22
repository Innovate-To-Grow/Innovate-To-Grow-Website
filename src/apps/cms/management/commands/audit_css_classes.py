import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.cms.services.styles.audit import audit_css_classes, default_frontend_dir, is_undefined


class Command(BaseCommand):
    help = (
        "List the CSS classes that stored CMS content uses (block HTML, footer HTML, page_css_class) and "
        "what styles each: active stylesheet rows, frontend CSS, a page's own page_css, or nothing. Report only."
    )

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
        parser.add_argument("--frontend-dir", metavar="PATH", help="Frontend source dir (default: pages/src).")
        parser.add_argument(
            "--no-frontend",
            action="store_true",
            help="Do not scan frontend CSS (for a server without pages/src); frontend-only classes read as undefined.",
        )
        parser.add_argument(
            "--undefined-only",
            action="store_true",
            help="Only list classes with no site-wide definition that are not a hook for other rules.",
        )

    def handle(self, *args, **options):
        scan_frontend = not options["no_frontend"]
        frontend_dir = Path(options["frontend_dir"] or default_frontend_dir())
        if scan_frontend and not frontend_dir.is_dir():
            raise CommandError(
                f"Frontend CSS directory not found: {frontend_dir}. "
                "Pass --frontend-dir PATH, or --no-frontend to report database sheets only."
            )
        report = audit_css_classes(frontend_dir=frontend_dir, scan_frontend=scan_frontend)
        if not scan_frontend:
            self.stderr.write("Frontend CSS not scanned: classes styled only in pages/src are reported as undefined.")
        elif not report["frontend_import_graph"]:
            self.stderr.write(f"No main.tsx in {frontend_dir}: every frontend CSS file counts as loaded on every page.")
        if options["undefined_only"]:
            report["classes"] = [row for row in report["classes"] if is_undefined(row)]
        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2))
            return
        self._write_table(report, undefined_only=options["undefined_only"])

    def _write_table(self, report, *, undefined_only):
        self.stdout.write(f"{'class':<40} {'uses':>5} {'places':>6}  styled by")
        for row in report["classes"]:
            self.stdout.write(
                f"{row['class_name']:<40} {row['usage_count']:>5} {self._places(row):>6}  {self._where(row)}"
            )
        total, undefined = report["total_classes"], report["undefined_classes"]
        if undefined_only:
            self.stdout.write(f"Showing the {undefined} undefined of {total} class(es) used in stored CMS content.")
        else:
            self.stdout.write(
                f"{total} class(es) used in stored CMS content, {undefined} with no site-wide definition."
            )

    @staticmethod
    def _places(row):
        return len(row["pages"]) + len(row["footers"])

    @staticmethod
    def _where(row):
        where = [f"sheet:{name}" for name in row["sheets"]] + row["frontend_files"]
        labelled = (
            ("route-only", row["route_frontend_files"]),
            ("page_css", row["page_css"]),
            ("inactive", row["inactive_sheets"]),
            ("scoped", row["scoped_in"]),
            ("hook", row["hook_in"]),
        )
        where += [f"{label}:{','.join(values)}" for label, values in labelled if values]
        return ", ".join(where) if where else "NOWHERE"
