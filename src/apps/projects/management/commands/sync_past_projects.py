from django.core.management.base import BaseCommand, CommandError

from apps.projects.models import PastProjectsSheetConfig
from apps.projects.services.sheet_sync import SheetSyncError, sync_past_projects


class Command(BaseCommand):
    help = "Sync the active PastProjectsSheetConfig from Google Sheets (if auto-sync is due)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Sync even if the interval has not elapsed.")

    def handle(self, *args, **options):
        config = PastProjectsSheetConfig.load()
        if not config:
            self.stdout.write(self.style.WARNING("No active past-projects sheet configuration found. Skipping."))
            return

        if not options["force"] and not config.sync_is_due:
            self.stdout.write(f"Auto-sync not due for '{config.name}'. Skipping.")
            return

        self.stdout.write(f"Syncing '{config.name}' from Google Sheets...")
        try:
            stats = sync_past_projects(config, sync_type="auto")
        except SheetSyncError as exc:
            # Raise CommandError so cron/CI supervisors that watch exit codes see the
            # failure rather than a silent exit 0 with stale data.
            raise CommandError(f"Sync failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"  Synced: {stats.projects_created} projects across {stats.semesters_touched} "
                f"semester(s); {stats.rows_skipped} rows skipped of {stats.rows_read} read."
            )
        )
