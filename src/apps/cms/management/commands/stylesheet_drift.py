import json

from django.core.management.base import BaseCommand, CommandError

from apps.cms.services.styles.drift import drift_report, drifted_sheets, export_rows


class Command(BaseCommand):
    help = (
        "Compare this database's StyleSheet rows with the repo seed (migrations/data/stylesheets.json). "
        "Exits with status 1 when the site serves CSS the seed lacks or a re-sync migration would change what "
        "it serves: an active sheet whose CSS differs from the seed or is not in it, a seed sheet whose active "
        "flag or order changed, or an active seed sheet that was deleted (a re-sync recreates it)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--diff", action="store_true", help="Print a unified diff for every edited sheet.")
        parser.add_argument("--json", action="store_true", help="Print the full report as JSON instead of a table.")
        parser.add_argument("--export", metavar="PATH", help="Write every sheet and every page_css to a JSON file.")
        parser.add_argument("--seed", metavar="PATH", help="Compare against another seed file of the same shape.")

    def handle(self, *args, **options):
        report = drift_report(seed_path=options["seed"])
        if not report["seed_found"]:
            raise CommandError(f"Seed file not found: {report['seed_path']}")
        if options["export"]:
            with open(options["export"], "w", encoding="utf-8") as handle:
                json.dump(export_rows(), handle, indent=2, ensure_ascii=False)
            self.stderr.write(f"Exported {len(report['sheets'])} sheet(s) to {options['export']}")
        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2))
        else:
            self._write_table(report, show_diff=options["diff"])
        drifted = drifted_sheets(report)
        if drifted:
            raise CommandError(
                f"{len(drifted)} sheet(s) differ from the repo seed: {', '.join(drifted)}. "
                "Port the wanted changes into the repo (or restore deleted sheets) before a migration re-syncs them."
            )

    def _write_table(self, report, *, show_diff):
        self.stdout.write(f"Seed: {report['seed_path']}")
        self.stdout.write(f"{'status':<17} {'on':<4} {'name':<30} {'changes':>10}  settings")
        for entry in report["sheets"]:
            changes = f"+{entry['added_lines']}/-{entry['removed_lines']}" if entry["status"] == "edited" else ""
            active = "on" if entry["is_active"] else "off"
            settings = ", ".join(entry["changed_settings"])
            line = f"{entry['status']:<17} {active:<4} {entry['name']:<30} {changes:>10}  {settings}"
            self.stdout.write(line.rstrip())
        for name in report["missing_from_database"]:
            self.stdout.write(f"{'missing':<17} {'':<4} {name:<30} {'(in seed only)':>10}")
        pages = report["pages_with_css"]
        self.stdout.write(f"Pages with page_css: {len(pages)}")
        for page in pages:
            self.stdout.write(f"  {page['route']} ({page['status']}, {page['page_css_length']} chars)")
        if show_diff:
            for entry in report["sheets"]:
                if entry["diff"]:
                    self.stdout.write(entry["diff"])
