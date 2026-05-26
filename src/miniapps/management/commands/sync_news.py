from django.core.management.base import BaseCommand

from miniapps.services.news import sync_news


class Command(BaseCommand):
    help = "Sync news articles from RSS feed into the News MiniApp data records."

    def add_arguments(self, parser):
        parser.add_argument("--feed-url", type=str, default=None, help="Override the default RSS feed URL")

    def handle(self, *args, **options):
        feed_url = options.get("feed_url")
        self.stdout.write("Starting news sync...")

        result = sync_news(feed_url=feed_url)

        self.stdout.write(f"Created: {result['created']}, Updated: {result['updated']}")
        if result["errors"]:
            for error in result["errors"]:
                self.stderr.write(self.style.WARNING(f"  {error}"))
        else:
            self.stdout.write(self.style.SUCCESS("Sync completed successfully."))
