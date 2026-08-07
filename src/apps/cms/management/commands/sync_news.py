from django.core.management.base import BaseCommand, CommandError

from apps.cms.models import NewsFeedSource
from apps.cms.services.news import sync_feed_sources


class Command(BaseCommand):
    help = "Sync news articles from all active configured RSS feeds"

    def handle(self, *args, **options):
        sources = list(NewsFeedSource.objects.filter(is_active=True))
        if not sources:
            raise CommandError("No active news feed sources found; refusing to report a successful no-op sync.")

        self.stdout.write(f"Syncing {len(sources)} active news feed(s)...")
        result = sync_feed_sources(sources)

        for feed_result in result["feeds"]:
            source = feed_result["source"]
            self.stdout.write(f"  {source.name}: {feed_result['created']} created, {feed_result['updated']} updated")
            for warning in feed_result["warnings"]:
                self.stderr.write(self.style.WARNING(f"  Warning ({source.name}): {warning}"))
            for error in feed_result["errors"]:
                self.stderr.write(self.style.ERROR(f"  Error ({source.name}): {error}"))

        summary = (
            f"Sync complete: {result['created']} created, {result['updated']} updated "
            f"across {result['feed_count']} feed(s)."
        )
        if result["errors"]:
            raise CommandError(f"{summary} {len(result['errors'])} error(s).")
        if result["warnings"]:
            self.stderr.write(self.style.WARNING(f"{summary} {len(result['warnings'])} warning(s)."))
            return
        self.stdout.write(self.style.SUCCESS(summary))
