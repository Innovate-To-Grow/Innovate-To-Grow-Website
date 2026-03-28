from django.core.management.base import BaseCommand

from pages.services.news import sync_news


class Command(BaseCommand):
    help = "Sync news articles from UC Merced RSS feed"

    def handle(self, *args, **options):
        self.stdout.write("Syncing news from RSS feed...")
        result = sync_news()
        self.stdout.write(f"  Created: {result['created']}")
        self.stdout.write(f"  Updated: {result['updated']}")
        if result["errors"]:
            for error in result["errors"]:
                self.stderr.write(self.style.WARNING(f"  Error: {error}"))
        self.stdout.write(self.style.SUCCESS("Sync complete."))
