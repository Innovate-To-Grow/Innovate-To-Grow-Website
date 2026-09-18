from django.core.management.base import BaseCommand, CommandError

from apps.event.services import ScheduleSyncError, resolve_sync_targets, sync_schedule


class Command(BaseCommand):
    help = (
        "Sync CurrentProjectSchedule rows from their Google Sheets. "
        "By default every schedule whose auto-sync is enabled and due is synced (active first). "
        "--schedule <uuid> syncs that one schedule now (any row, regardless of its auto-sync settings); "
        "--force syncs the active schedule now, ignoring its auto-sync interval."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Sync even if the interval has not elapsed. Without --schedule this syncs the active schedule only.",
        )
        parser.add_argument(
            "--schedule",
            dest="schedule_id",
            default="",
            help=(
                "UUID of a specific CurrentProjectSchedule to sync now (any row, not only the active one; "
                "its auto-sync settings are ignored)."
            ),
        )

    def handle(self, *args, **options):
        # An explicitly targeted schedule is an operator asking for a sync now —
        # archived rows have auto-sync switched off, so never gate them on it.
        force = options["force"] or bool(options["schedule_id"])
        try:
            targets = resolve_sync_targets(options["schedule_id"], force=force)
        except ScheduleSyncError as exc:
            raise CommandError(str(exc)) from exc
        if not targets:
            missing = "No active schedule configuration found." if force else "No schedule configuration found."
            self.stdout.write(self.style.WARNING(f"{missing} Skipping."))
            return

        failures = []
        for config in targets:
            if not force and not config.sync_is_due:
                self.stdout.write(f"Auto-sync not due for '{config.name}'. Skipping.")
                continue

            self.stdout.write(f"Syncing '{config.name}' from Google Sheets...")
            try:
                stats = sync_schedule(config, sync_type="auto")
            except ScheduleSyncError as exc:
                # Keep going so one broken sheet does not block the other
                # schedules; the aggregated CommandError below still makes
                # cron/CI supervisors that only watch exit codes see the failure.
                failures.append(f"'{config.name}': {exc}")
                self.stderr.write(self.style.ERROR(f"  Sync failed for '{config.name}': {exc}"))
                continue

            self.stdout.write(self.style.SUCCESS(f"  Synced: {stats.summary()}"))

        if failures:
            raise CommandError("Sync failed: " + "; ".join(failures))
