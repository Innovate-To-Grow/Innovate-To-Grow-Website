from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.system_intelligence.models import AssistantConversationLog, SystemIntelligenceConfig


class Command(BaseCommand):
    help = "Delete audited assistant conversations older than the configured retention window."

    def handle(self, *args, **options):
        config = SystemIntelligenceConfig.load()
        retention_days = config.public_assistant_log_retention_days
        if not retention_days:
            self.stdout.write("Retention is set to 0 (keep forever); nothing to delete.")
            return

        cutoff = timezone.now() - timedelta(days=retention_days)
        deleted, _ = AssistantConversationLog.objects.filter(last_activity_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Removed {deleted} record(s) older than {retention_days} day(s)."))
