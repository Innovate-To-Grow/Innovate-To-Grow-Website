from django.core.management.base import BaseCommand

from apps.system_intelligence.services.usage_log import (
    conversation_log_retention_days,
    purge_expired_conversation_logs,
)


class Command(BaseCommand):
    help = (
        "Delete audited assistant conversations older than the configured retention window, in batches. "
        "Nothing runs this automatically; schedule it if the retention setting should take effect."
    )

    def handle(self, *args, **options):
        retention_days = conversation_log_retention_days()
        if not retention_days:
            self.stdout.write("Retention is set to 0 (keep forever), or no configuration is active; nothing to delete.")
            return

        deleted = purge_expired_conversation_logs()
        self.stdout.write(self.style.SUCCESS(f"Removed {deleted} record(s) older than {retention_days} day(s)."))
