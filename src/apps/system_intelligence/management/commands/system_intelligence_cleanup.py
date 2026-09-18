from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.system_intelligence.models import (
    AssistantConversationLog,
    SystemIntelligenceConfig,
    SystemIntelligenceExport,
)


class Command(BaseCommand):
    help = (
        "Delete audited assistant conversations and AI-generated exports older than their configured retention windows."
    )

    def handle(self, *args, **options):
        config = SystemIntelligenceConfig.load()
        self._cleanup_conversation_logs(config.public_assistant_log_retention_days)
        self._cleanup_exports(config.export_retention_days)

    def _cleanup_conversation_logs(self, retention_days):
        if not retention_days:
            self.stdout.write("Retention is set to 0 (keep forever); nothing to delete.")
            return

        cutoff = timezone.now() - timedelta(days=retention_days)
        deleted, _ = AssistantConversationLog.objects.filter(last_activity_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Removed {deleted} record(s) older than {retention_days} day(s)."))

    def _cleanup_exports(self, retention_days):
        if not retention_days:
            self.stdout.write("Export retention is set to 0 (keep forever); no exports deleted.")
            return

        cutoff = timezone.now() - timedelta(days=retention_days)
        # QuerySet.delete() still fires post_delete per row, which removes each file from storage.
        deleted, _ = SystemIntelligenceExport.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Removed {deleted} export(s) older than {retention_days} day(s)."))
