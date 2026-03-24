from django.core.management.base import BaseCommand, CommandError

from sheets.models import SheetLink
from sheets.services.sync import pull_from_sheet


class Command(BaseCommand):
    help = "Pull data from Google Sheets into the database."

    def add_arguments(self, parser):
        parser.add_argument("--link-id", type=str, help="Pull a specific SheetLink by UUID")
        parser.add_argument("--name", type=str, help="Pull a specific SheetLink by name (case-insensitive)")

    def handle(self, *args, **options):
        link_id = options.get("link_id")
        name = options.get("name")

        if link_id:
            try:
                links = [SheetLink.objects.get(pk=link_id)]
            except SheetLink.DoesNotExist:
                raise CommandError(f"SheetLink with id '{link_id}' not found.")
        elif name:
            links = list(SheetLink.objects.filter(name__icontains=name, is_active=True))
            if not links:
                raise CommandError(f"No active SheetLink matching name '{name}'.")
        else:
            links = list(
                SheetLink.objects.filter(
                    is_active=True,
                    sync_direction__in=["pull", "both"],
                )
            )
            if not links:
                self.stdout.write("No active pull-eligible SheetLinks found.")
                return

        self.stdout.write(f"Pulling {len(links)} link(s)...\n")

        for link in links:
            self.stdout.write(f"  {link.name} ... ", ending="")
            log = pull_from_sheet(link)
            self.stdout.write(
                f"{log.get_status_display()} — "
                f"{log.rows_created} created, {log.rows_updated} updated, "
                f"{log.rows_skipped} skipped, {log.rows_failed} failed"
            )
            if log.error_details:
                for err in log.error_details[:5]:
                    self.stderr.write(f"    Row {err['row']}: {err['error']}")
                if len(log.error_details) > 5:
                    self.stderr.write(f"    ... and {len(log.error_details) - 5} more errors")

        self.stdout.write(self.style.SUCCESS("Done."))
