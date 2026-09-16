from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.event.models import CurrentProjectSchedule
from apps.event.services import ScheduleSyncError, sync_schedule


class Command(BaseCommand):
    help = (
        "Sync CurrentProjectSchedule rows from their Google Sheets. "
        "By default every schedule whose auto-sync is enabled and due is synced (active first). "
        "Use --schedule <uuid> to target one schedule; --force ignores the auto-sync interval "
        "(and, without --schedule, syncs the active schedule)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Sync even if the interval has not elapsed.")
        parser.add_argument(
            "--schedule",
            dest="schedule_id",
            default="",
            help="UUID of a specific CurrentProjectSchedule to sync (any row, not only the active one).",
        )

    def handle(self, *args, **options):
        force = options["force"]
        targets = self._resolve_targets(options["schedule_id"], force)
        if not targets:
            self.stdout.write(self.style.WARNING("No active schedule configuration found. Skipping."))
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

            self.stdout.write(
                self.style.SUCCESS(
                    f"  Synced: {stats.sections_created} sections, "
                    f"{stats.tracks_created} tracks, "
                    f"{stats.slots_created} slots, "
                    f"{stats.unmatched_slots} unmatched."
                )
            )

        if failures:
            raise CommandError("Sync failed: " + "; ".join(failures))

    def _resolve_targets(self, schedule_id, force):
        if schedule_id:
            try:
                config = CurrentProjectSchedule.objects.filter(pk=schedule_id).first()
            except (TypeError, ValueError, ValidationError):
                config = None
            if config is None:
                raise CommandError(f"No CurrentProjectSchedule found with id '{schedule_id}'.")
            return [config]

        if force:
            # Historical behaviour: a forced run without a target syncs the
            # active schedule only, so operators' manual runs stay predictable.
            config = CurrentProjectSchedule.load()
            return [config] if config else []

        # Cron mode: consider every schedule (each row carries its own sheet and
        # auto-sync settings); the active one goes first.
        return list(CurrentProjectSchedule.objects.order_by("-is_active", "-created_at"))
