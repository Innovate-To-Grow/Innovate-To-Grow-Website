from django.core.management.base import BaseCommand

from authn.services.member_sheet_sync import MemberSyncError, sync_members_to_sheet


class Command(BaseCommand):
    help = "Sync all members to the configured Google Sheet"

    def handle(self, *args, **options):
        self.stdout.write("Syncing members to Google Sheet...")
        try:
            rows = sync_members_to_sheet(sync_type="scheduled")
            self.stdout.write(self.style.SUCCESS(f"Synced {rows} members to sheet."))
        except MemberSyncError as exc:
            self.stderr.write(self.style.ERROR(f"Sync failed: {exc}"))
