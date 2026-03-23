from django.core.management.base import BaseCommand

from projects.services.sync_sheets import sync_all_project_sheets, sync_from_sheet


class Command(BaseCommand):
    help = "Sync project data from Google Sheets into the database"

    def add_arguments(self, parser):
        parser.add_argument("--slug", type=str, help="Sync only the GoogleSheetSource with this slug")
        parser.add_argument("--spreadsheet-id", type=str, help="Google Spreadsheet ID (for direct sync)")
        parser.add_argument("--range", type=str, help="A1 range notation (for direct sync)")
        parser.add_argument(
            "--type",
            type=str,
            choices=["current-event", "past-projects", "archive-event"],
            help="Sheet type (for direct sync)",
        )
        parser.add_argument("--semester-filter", type=str, default="", help="Filter rows by semester value")

    def handle(self, *args, **options):
        spreadsheet_id = options.get("spreadsheet_id")
        range_a1 = options.get("range")
        sheet_type = options.get("type")
        slug = options.get("slug")

        if spreadsheet_id and range_a1 and sheet_type:
            # Direct sync with explicit params
            self.stdout.write(f"Syncing from spreadsheet {spreadsheet_id} ({sheet_type})...")
            stats = sync_from_sheet(spreadsheet_id, range_a1, sheet_type, options["semester_filter"])
            self._print_stats(stats)
            return

        if slug:
            # Sync a specific GoogleSheetSource by slug
            from sheets.models import GoogleSheetSource

            try:
                source = GoogleSheetSource.objects.get(slug=slug, is_active=True)
            except GoogleSheetSource.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"No active GoogleSheetSource with slug '{slug}'."))
                return

            self.stdout.write(f"Syncing '{source.slug}' ({source.sheet_type})...")
            stats = sync_from_sheet(
                spreadsheet_id=source.spreadsheet_id,
                range_a1=source.range_a1,
                sheet_type=source.sheet_type,
                semester_filter=source.semester_filter,
            )
            self._print_stats(stats)
            return

        # Sync all project sheets
        self.stdout.write("Syncing all project sheets...")
        result = sync_all_project_sheets()
        self.stdout.write(f"  Sources synced: {result['sources_synced']}")
        self._print_stats(result)
        if result["errors"]:
            for error in result["errors"]:
                self.stderr.write(self.style.WARNING(f"  Error: {error}"))
        self.stdout.write(self.style.SUCCESS("Sync complete."))

    def _print_stats(self, stats):
        self.stdout.write(f"  Semesters created: {stats['semesters_created']}")
        self.stdout.write(f"  Semesters existing: {stats['semesters_existing']}")
        self.stdout.write(f"  Projects created: {stats['projects_created']}")
        self.stdout.write(f"  Projects updated: {stats['projects_updated']}")
        self.stdout.write(f"  Rows skipped: {stats['rows_skipped']}")
