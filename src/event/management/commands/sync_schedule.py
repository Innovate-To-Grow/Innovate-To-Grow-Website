from django.core.management.base import BaseCommand

from event.models import CurrentProjectSchedule
from event.services import ScheduleSyncError, sync_schedule


class Command(BaseCommand):
    help = "Sync the active CurrentProjectSchedule from Google Sheets (if auto-sync is due)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Sync even if the interval has not elapsed.")

    def handle(self, *args, **options):
        config = CurrentProjectSchedule.load()
        if not config:
            self.stdout.write(self.style.WARNING("No active schedule configuration found. Skipping."))
            return

        if not options["force"] and not config.sync_is_due:
            self.stdout.write(f"Auto-sync not due for '{config.name}'. Skipping.")
            return

        self.stdout.write(f"Syncing '{config.name}' from Google Sheets...")
        try:
            stats = sync_schedule(config)
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Synced: {stats.sections_created} sections, "
                    f"{stats.tracks_created} tracks, "
                    f"{stats.slots_created} slots, "
                    f"{stats.unmatched_slots} unmatched."
                )
            )
        except ScheduleSyncError as exc:
            self.stderr.write(self.style.ERROR(f"  Sync failed: {exc}"))
