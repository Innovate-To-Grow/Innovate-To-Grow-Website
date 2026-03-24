from django.core.management.base import BaseCommand, CommandError

from sheets.models import SheetLink
from sheets.services.sync import push_to_sheet


class Command(BaseCommand):
    help = "Push data from the database to Google Sheets."

    def add_arguments(self, parser):
        parser.add_argument("--link-id", type=str, help="Push a specific SheetLink by UUID")
        parser.add_argument("--name", type=str, help="Push a specific SheetLink by name (case-insensitive)")

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
                    sync_direction__in=["push", "both"],
                )
            )
            if not links:
                self.stdout.write("No active push-eligible SheetLinks found.")
                return

        self.stdout.write(f"Pushing {len(links)} link(s)...\n")

        for link in links:
            self.stdout.write(f"  {link.name} ... ", ending="")
            log = push_to_sheet(link)
            self.stdout.write(f"{log.get_status_display()} — {log.rows_created} rows written, {log.rows_failed} failed")
            if log.error_details:
                for err in log.error_details[:5]:
                    self.stderr.write(f"    Row {err['row']}: {err['error']}")
                if len(log.error_details) > 5:
                    self.stderr.write(f"    ... and {len(log.error_details) - 5} more errors")

        self.stdout.write(self.style.SUCCESS("Done."))
